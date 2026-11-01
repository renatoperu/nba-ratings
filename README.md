# NBA Glicko-2 Ratings (personal app)

Installable web app with NBA team ratings from 1946 to the live 2026-27 season.
A scheduled GitHub job refreshes `data/season.json` (schedule and results) every 4 hours and republishes the app.

## One-time setup (about 10 minutes, free)

1. Create a free account at github.com and make a **new repository** (name it e.g. `nba-ratings`; Public is simplest).
2. Upload everything in this folder to the repository root (web: *Add file -> Upload files*, drag the contents in).
   If the hidden `.github` folder did not upload, choose *Add file -> Create new file*, type the name
   `.github/workflows/update.yml` and paste the contents of that file from this folder.
3. In the repository go to **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.
4. Go to the **Actions** tab, open "Update data and publish" and press **Run workflow**. After about a minute your app is at
   `https://<your-user>.github.io/<repo-name>/`.
5. On your phone open that address:
   - **iPhone (Safari):** Share -> Add to Home Screen.
   - **Android (Chrome):** menu -> Install app / Add to Home screen.

The app works offline after the first visit and checks for new results each time you open it (and under
Add / Import -> Check for updates now).

## Notes

- Results you type in the app are kept on that device and are never overwritten by the automatic file.
- The job reads ESPN's schedule table from the public `sportsdataverse/hoopR-nba-data` repository, which is itself refreshed about daily,
  so a result can show up a few hours after the game.
- Next season: change `SEASON_YEAR` in `scripts/update_season.py` (2028 = the 2027-28 season) and rebuild the app file.
- GitHub pauses scheduled jobs in repositories with no activity for 60 days; press **Run workflow** to wake it.
- To test the data script locally: `pip install pandas pyarrow requests && python scripts/update_season.py`.

## WNBA

`wnba.html` is the WNBA version of the same app (2002–2026, live 2026 season). The NBA | WNBA | NHL switch at the top of every page moves between them, and the app opens on the league you used last. `scripts/update_season.py --league wnba` writes `data/wnba-season.json`; the workflow runs all three leagues.

## Faster results (ESPN)

`scripts/update_season.py` reads the daily hoopR/wehoop table first, then re-reads the last few days from ESPN's live scoreboard and fills in any results that the table doesn't have yet (it never adds unplayed games from ESPN). If ESPN can't be reached or its format changes, the run logs a warning and keeps the hoopR data. The workflow log line to look for: `ESPN nba: N events over 5 days, ... filled X results ... 0 day(s) failed`. Use `--no-espn` to turn it off.

## NHL

`nhl.html` is the NHL version: every game since 1917-18 (108 seasons; there was no 2004-05 season) plus the live 2026-27 season. Ratings use goal difference, a shootout counts as a one-goal win, ties before 2005 count as half a win, and standings use points (2 for a win, 1 for a tie, and from 1999-2000 1 for an overtime or shootout loss). `scripts/update_season.py --league nhl` writes `data/nhl-season.json`. The division alignment is hard-coded in `league_nhl.js` (in the build sources), so a realignment needs a rebuild.

## MLB

`mlb.html` is the MLB version: every American and National League game since 1901 (126 seasons, regular season and postseason) plus the live 2027 season. Ratings use run margin; ties (rare, early seasons) count as half a win; standings and the simulator use today's six divisions and the 12-team playoff (three division winners and three wild cards per league, byes for the top two, best-of-3, 5, 7, 7 with the 2-2-1 and 2-3-2 home patterns). `scripts/update_season.py --league mlb` reads the MLB Stats API schedule (`statsapi.mlb.com`) and writes `data/mlb-season.json`; there is no ESPN overlay. The 2027 schedule appears there once MLB publishes it, and until then the app simply starts with an empty season. Doubleheaders are supported. Log lines to look for: `Wrote N games (M with results)` or `No changes`. History: Retrosheet game logs plus the Stats API tables for 2024 and 2026; the Federal League is excluded. Division alignment is hard-coded in `league_mlb.js`, so a realignment needs a rebuild.

## NFL

`nfl.html` is the NFL version: every game of the Super Bowl era (1966 to 2025, 60 seasons, 14,413 games including the AFL years) plus the live 2026 season. Ratings use point margin; ties count as half a win (live ties included). The simulator uses today's 14-team playoff: four division winners and three wild cards per conference, top seed with a bye, the top seed meeting the lowest survivor in the second round, and a neutral-site Super Bowl. `scripts/update_season.py --league nfl` reads the nflverse games table (`nflverse/nfldata`) and then ESPN's scoreboard for the last few days; the season year rolls over every March (or set `NFL_SEASON_YEAR`). Division alignment is hard-coded in `league_nfl.js`. Highest and lowest ratings in the Records tab only count days when the team's RD is low enough (a per-league cutoff `recRD` in each league file), so a new team's first volatile seasons cannot set a record.
