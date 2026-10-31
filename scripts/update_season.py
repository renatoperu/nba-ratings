#!/usr/bin/env python3
"""Refresh data/season.json (NBA) or data/wnba-season.json (WNBA) with the current season's schedule and results.

Source: the ESPN schedule table published by sportsdataverse/hoopR-nba-data on GitHub
(nba_schedule_<YYYY>.parquet, where YYYY is the year the season ends, e.g. 2027 for 2026-27).

Usage:
    python scripts/update_season.py                 # uses SEASON_YEAR below (or env SEASON_YEAR)
    python scripts/update_season.py --source file.parquet --out /tmp/season.json

The file is only rewritten when the games changed, so a scheduled run that finds nothing new
produces no commit. On a download or parsing failure the existing file is left untouched.
"""
import argparse, io, json, os, re, sys, datetime as dt
import pandas as pd

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard?dates={d}&limit=300"
ESPN_DAYS_BACK = 3   # how many past days (ET) are re-read from ESPN on every run

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
LEAGUES = {
    "nba": dict(
        year=int(os.environ.get("SEASON_YEAR", "2027")),      # 2027 = the 2026-27 season; change it once a year
        url="https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/schedules/parquet/nba_schedule_{y}.parquet",
        out=os.path.join(DATA, "season.json"), src="hoopR-nba-data", sport="basketball/nba",
        abbr={"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"},
        fr=set("ATL BKN BOS CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split())),
    "wnba": dict(
        year=int(os.environ.get("WNBA_SEASON_YEAR", "2026")),  # WNBA seasons sit inside one calendar year
        url="https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-data/main/wnba/schedules/parquet/wnba_schedule_{y}.parquet",
        out=os.path.join(DATA, "wnba-season.json"), src="wehoop-wnba-data", sport="basketball/wnba",
        abbr={"GS": "GSV", "LV": "LVA", "LA": "LAS", "NY": "NYL", "WSH": "WAS", "POR": "PDX"},
        fr=set("ATL CHI CON DAL GSV IND LAS LVA MIN NYL PDX PHX SEA TOR WAS".split())),
    "nhl": dict(
        year=int(os.environ.get("NHL_SEASON_YEAR", "2027")),    # 2027 = the 2026-27 season
        url="https://raw.githubusercontent.com/sportsdataverse/fastRhockey-nhl-data/main/nhl/schedules/parquet/nhl_schedule_{y}.parquet",
        goals_url="https://raw.githubusercontent.com/sportsdataverse/fastRhockey-nhl-data/main/nhl/scoring/parquet/scoring_{y}.parquet",
        out=os.path.join(DATA, "nhl-season.json"), src="fastRhockey-nhl-data", sport="hockey/nhl", ot=True,
        # ESPN abbreviations that differ from the data repository's
        abbr={"LA": "LAK", "NJ": "NJD", "SJ": "SJS", "TB": "TBL", "UTAH": "UTA", "ARI": "UTA", "PHX": "UTA", "VEG": "VGK"},
        fr=set("ANA BOS BUF CAR CBJ CGY CHI COL DAL DET EDM FLA LAK MIN MTL NJD NSH NYI NYR OTT PHI PIT SEA SJS STL TBL TOR UTA VAN VGK WPG WSH".split())),
}
UNKNOWN = set()    # team abbreviations ESPN sent that we could not map (reported in the log)
L = LEAGUES["nba"]


def load(source, year):
    if source:
        return pd.read_parquet(source)
    import requests
    r = requests.get(L["url"].format(y=year), timeout=60)
    r.raise_for_status()
    return pd.read_parquet(io.BytesIO(r.content))


def game_type(season_type, headline):
    h = (headline or "")
    if L is LEAGUES["nhl"]:
        return "P" if season_type == 3 else "R"
    if L is LEAGUES["wnba"]:
        if season_type == 3:
            return "P"
        if "Championship" in h:
            return "F"      # Commissioner's Cup final: not part of the standings
        return "C" if "Commissioner" in h else "R"
    if season_type == 5:
        return "I"
    if season_type == 3:
        return "P"
    if "Championship" in h:
        return "F"          # NBA Cup final: not part of the standings
    if "Cup" in h:
        return "C"          # Cup group and knockout games count in the standings
    return "R"


def convert(df):
    rows = []
    for r in df.itertuples():
        if r.season_type not in (2, 3, 5):
            continue
        h = r.notes_headline if isinstance(r.notes_headline, str) else ""
        if "All-Star" in h:
            continue
        a = L["abbr"].get(r.away_abbreviation, r.away_abbreviation)
        b = L["abbr"].get(r.home_abbreviation, r.home_abbreviation)
        if a not in L["fr"] or b not in L["fr"]:
            continue                                   # e.g. Cup knockout slots still marked TBD
        done = (r.status_type_name == "STATUS_FINAL" and pd.notna(r.home_score) and pd.notna(r.away_score))
        ap = int(r.away_score) if done else None
        hp = int(r.home_score) if done else None
        if done and ap == hp:
            ap = hp = None
        if r.status_type_name in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            continue
        rows.append([str(r.game_date)[:10], a, b, game_type(int(r.season_type), h), 1 if bool(r.neutral_site) else 0, ap, hp])
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    return rows


def goal_ids(year):
    """ids of games with an overtime goal (from the goal log); empty set when the table cannot be read."""
    try:
        import requests
        r = requests.get(L["goals_url"].format(y=year), timeout=90)
        r.raise_for_status()
        sc = pd.read_parquet(io.BytesIO(r.content), columns=["game_id", "period_type"])
        return set(sc[sc.period_type == "OT"].game_id), True
    except Exception as e:
        print("WARNING: goal log unavailable (%s); overtime flags come from the previous file" % e)
        return set(), False


def convert_nhl(df, ot_ids, have_goals, old_ex):
    rows = []
    for r in df.sort_values(["game_date", "game_id"]).itertuples():
        if r.game_type not in ("R", "P"):
            continue
        a = L["abbr"].get(r.away_team_abbr, r.away_team_abbr)
        b = L["abbr"].get(r.home_team_abbr, r.home_team_abbr)
        if a not in L["fr"] or b not in L["fr"]:
            continue
        done = (r.game_state in ("OFF", "FINAL") and pd.notna(r.home_score) and pd.notna(r.away_score) and int(r.home_score) != int(r.away_score))
        ap = int(r.away_score) if done else None
        hp = int(r.home_score) if done else None
        key = (str(r.game_date)[:10], a, b)
        if not done:
            ex = 0
        elif bool(getattr(r, "shootout", False)):
            ex = 2
        elif have_goals:
            ex = 1 if r.game_id in ot_ids else 0
        else:
            ex = old_ex.get(key, 0)
        rows.append([key[0], a, b, game_type(2 if r.game_type == "R" else 3, ""), 0, ap, hp, ex])
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    return rows


def espn_type(season_type, headline):
    """Same game types as the hoopR path, from an ESPN scoreboard event."""
    return game_type(season_type, headline)


def parse_espn(payload):
    """ESPN scoreboard JSON -> rows [date(ET), away, home, type, neutral, awayPts|None, homePts|None]. Unknown shapes raise."""
    rows = []
    for ev in payload["events"]:
        comp = ev["competitions"][0]
        st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
        name = st.get("name", "")
        if name in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_TBD"):
            continue
        home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
        away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
        notes = comp.get("notes") or ev.get("notes") or []
        headline = notes[0].get("headline", "") if notes else ""
        if "All-Star" in headline:
            continue
        a = L["abbr"].get(away["team"]["abbreviation"], away["team"]["abbreviation"])
        b = L["abbr"].get(home["team"]["abbreviation"], home["team"]["abbreviation"])
        if a not in L["fr"] or b not in L["fr"]:
            UNKNOWN.update(x for x in (a, b) if x not in L["fr"])
            continue
        stype = int((ev.get("season") or {}).get("type", 2))
        if stype not in (2, 3, 5):
            continue
        day = pd.Timestamp(ev["date"]).tz_convert("America/New_York").strftime("%Y-%m-%d")
        done = name == "STATUS_FINAL"
        ap = int(float(away["score"])) if done else None
        hp = int(float(home["score"])) if done else None
        if done and ap == hp:
            ap = hp = None
        row = [day, a, b, espn_type(stype, headline), 1 if comp.get("neutralSite") else 0, ap, hp]
        if L.get("ot"):
            detail = " ".join(str(st.get(k, "")) for k in ("detail", "shortDetail", "description")).upper()
            row.append(0 if not done else (2 if re.search(r"\bSO\b|SHOOTOUT", detail) else (1 if re.search(r"OT", detail) else 0)))
        rows.append(row)
    return rows


def fetch_espn(lg, days, fixture_dir=None):
    """One request per day; returns (rows, errors). Never raises."""
    rows, errors = [], []
    for d in days:
        key = d.replace("-", "")
        try:
            if fixture_dir:
                with open(os.path.join(fixture_dir, key + ".json")) as f:
                    payload = json.load(f)
            else:
                import requests
                r = requests.get(ESPN.format(sport=LEAGUES[lg]["sport"], d=key), timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; ratings-app)"})
                r.raise_for_status()
                payload = r.json()
            rows += parse_espn(payload)
        except FileNotFoundError:
            pass
        except Exception as e:                      # network, JSON shape, anything: skip this day, keep the rest
            errors.append("%s: %s: %s" % (key, type(e).__name__, e))
    return rows, errors


def overlay_espn(games, lg, today, fixture_dir=None):
    """Fill results (and add games) from ESPN's live scoreboard for the last few days. The hoopR rows stay the base."""
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(ESPN_DAYS_BACK, -2, -1)]
    espn, errors = fetch_espn(lg, days, fixture_dir)
    idx = {(g[0], g[1], g[2]): g for g in games}
    filled = added = changed = 0
    for r in espn:
        g = idx.get((r[0], r[1], r[2]))
        if g is None and r[5] is not None:
            # same teams a day either side, still without a result: the same game under a shifted date (UTC vs ET)
            day = dt.date.fromisoformat(r[0])
            for off in (-1, 1):
                c = idx.get(((day + dt.timedelta(days=off)).isoformat(), r[1], r[2]))
                if c is not None and c[5] is None:
                    g = c
                    break
        if g is None:
            if r[5] is None:
                continue                      # never add unplayed games from ESPN; the schedule comes from hoopR
            games.append(list(r)); idx[(r[0], r[1], r[2])] = games[-1]; added += 1
            continue
        hk = len(g) > 7 and len(r) > 7
        if r[5] is not None and (g[5] != r[5] or g[6] != r[6] or (hk and g[7] < r[7])):
            # overtime flag: take ESPN's when the result is new or corrected; otherwise only ever raise it (never lose an overtime flag the data table had)
            ex = (r[7] if (g[5] is None or g[5] != r[5] or g[6] != r[6]) else max(g[7], r[7])) if hk else None
            if g[5] is None: filled += 1
            else: changed += 1
            g[5], g[6] = r[5], r[6]
            if hk: g[7] = ex
    games.sort(key=lambda x: (x[0], x[1], x[2]))
    print("ESPN %s: %d events over %d days, %d finished; filled %d results, %d corrected, %d games added; %d day(s) failed%s" % (
        lg, len(espn), len(days), sum(1 for r in espn if r[5] is not None), filled, changed, added, len(errors),
        ("  [" + "; ".join(errors[:3]) + "]") if errors else "") + (("  unmapped ESPN teams: " + ", ".join(sorted(UNKNOWN))) if UNKNOWN else ""))
    return games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=sorted(LEAGUES), default="nba")
    ap.add_argument("--source")
    ap.add_argument("--out")
    ap.add_argument("--year", type=int)
    ap.add_argument("--goals", help="NHL only: local scoring parquet (tests); default is downloaded")
    ap.add_argument("--no-espn", action="store_true", help="use only the hoopR table")
    ap.add_argument("--espn-fixture", help="directory of YYYYMMDD.json files to read instead of the ESPN API (tests)")
    ap.add_argument("--today", help="YYYY-MM-DD (ET); default: today")
    args = ap.parse_args()
    global L
    L = LEAGUES[args.league]
    args.out = args.out or L["out"]
    args.year = args.year or L["year"]
    try:
        df = load(args.source, args.year)
        if args.league == "nhl":
            old_ex = {}
            try:
                with open(args.out) as f:
                    for g in json.load(f).get("games", []):
                        if len(g) > 7: old_ex[(g[0], g[1], g[2])] = g[7]
            except Exception:
                pass
            if args.goals:
                sc = pd.read_parquet(args.goals, columns=["game_id", "period_type"])
                ot_ids, have = set(sc[sc.period_type == "OT"].game_id), True
            elif args.source:
                ot_ids, have = set(), False
            else:
                ot_ids, have = goal_ids(args.year)
            games = convert_nhl(df, ot_ids, have, old_ex)
        else:
            games = convert(df)
        if not args.no_espn:
            today = dt.date.fromisoformat(args.today) if args.today else pd.Timestamp.now(tz="America/New_York").date()
            try:
                games = overlay_espn(games, args.league, today, args.espn_fixture)
            except Exception as e:
                print("WARNING: ESPN overlay skipped (%s: %s)" % (type(e).__name__, e))
        if len(games) < 100:
            raise RuntimeError("only %d games found; refusing to overwrite" % len(games))
    except Exception as e:
        print("WARNING: could not refresh the season data (%s). Keeping the existing file." % e)
        return 0
    old = None
    if os.path.exists(args.out):
        try:
            with open(args.out) as f:
                old = json.load(f)
        except Exception:
            old = None
    if old and old.get("season") == args.year and old.get("games") == games:
        print("No changes (%d games, %d with results)." % (len(games), sum(1 for g in games if g[5] is not None)))
        return 0
    out = {"season": args.year, "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "sportsdataverse/" + L["src"] + " + ESPN scoreboard", "games": games}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    from collections import Counter
    print("Wrote %d games (%d with results) to %s; types %s" % (len(games), sum(1 for g in games if g[5] is not None), args.out, dict(Counter(g[3] for g in games))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
