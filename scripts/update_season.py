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
import argparse, io, json, os, sys, datetime as dt
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
LEAGUES = {
    "nba": dict(
        year=int(os.environ.get("SEASON_YEAR", "2027")),      # 2027 = the 2026-27 season; change it once a year
        url="https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/schedules/parquet/nba_schedule_{y}.parquet",
        out=os.path.join(DATA, "season.json"), src="hoopR-nba-data",
        abbr={"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"},
        fr=set("ATL BKN BOS CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split())),
    "wnba": dict(
        year=int(os.environ.get("WNBA_SEASON_YEAR", "2026")),  # WNBA seasons sit inside one calendar year
        url="https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-data/main/wnba/schedules/parquet/wnba_schedule_{y}.parquet",
        out=os.path.join(DATA, "wnba-season.json"), src="wehoop-wnba-data",
        abbr={"GS": "GSV", "LV": "LVA", "LA": "LAS", "NY": "NYL", "WSH": "WAS", "POR": "PDX"},
        fr=set("ATL CHI CON DAL GSV IND LAS LVA MIN NYL PDX PHX SEA TOR WAS".split())),
}
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=sorted(LEAGUES), default="nba")
    ap.add_argument("--source")
    ap.add_argument("--out")
    ap.add_argument("--year", type=int)
    args = ap.parse_args()
    global L
    L = LEAGUES[args.league]
    args.out = args.out or L["out"]
    args.year = args.year or L["year"]
    try:
        df = load(args.source, args.year)
        games = convert(df)
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
           "source": "ESPN schedule via sportsdataverse/" + L["src"], "games": games}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    from collections import Counter
    print("Wrote %d games (%d with results) to %s; types %s" % (len(games), sum(1 for g in games if g[5] is not None), args.out, dict(Counter(g[3] for g in games))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
