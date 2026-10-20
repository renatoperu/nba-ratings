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
