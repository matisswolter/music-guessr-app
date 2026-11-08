# Music Guessr 🎵

Guess the **artist**, **title** and **release year** of songs from your own Spotify playlists.

> **Branch `deezer-previews`:** your playlists come from a file *you* export from Spotify, and the
> 30-second snippets are played in the app from **Deezer's** free preview API. This app never talks to the
> Spotify API, so no Spotify developer app, no Premium and no open Spotify device are needed.
> The Spotify-API version lives on `main`.

- 🎧 30-second Deezer previews, played right inside the app (no "now playing" spoilers)
- 📥 Import playlists from an [Exportify](https://exportify.net) CSV or from Spotify's "Download your data" export
- ✅ Fuzzy answer matching: `beatles` = *The Beatles*, `beyonce` = *Beyoncé*, *“– Remastered 2011”* is ignored
- 📚 Two collections: **guessed songs** (with album covers) and **guessed artists** (with artist photos),
  each linked to Wikipedia when an article exists
- 📊 A statistics page: points, streaks, accuracy rings, progress over time, accuracy by decade, top artists

## Tech stack: why Flet (Python)

The app is written in **Python with [Flet](https://flet.dev)**. Flet wraps Google's Flutter UI toolkit, so you
write plain Python and `flet build ipa` / `flet build apk` produce real iOS and Android apps from the same code.

| Option | Language | iOS + Android | Verdict |
|---|---|---|---|
| **Flet** | Python | ✅ one codebase | **Chosen.** Pure Python, Material 3 UI and built-in charts, active development |
| BeeWare (Toga + Briefcase) | Python | ✅ | Native widgets but few UI controls and no charts, so a fancy stats page is hard |
| Kivy / KivyMD | Python | ✅ (iOS painful) | Mature, but looks dated and iOS packaging via kivy-ios is fiddly |
| Flutter | Dart | ✅ | What Flet runs on. Pick it if you outgrow Flet. Dart is easy to learn coming from Python |
| React Native / Expo | TypeScript | ✅ | Best ecosystem (official Spotify SDK wrappers), but a new language |
| Swift (SwiftUI) | Swift | iOS only | Best iOS integration, but Android would need a second app |

**Trade-off:** Flet can't call native SDKs. Audio is played with Flet's own audio player, and if you later
need deeper native integration, the Flutter/Dart route stays open.

## Why import + Deezer instead of the Spotify API?

- Spotify's [Developer Policy](https://developer.spotify.com/policy) says "Do not create a game, including trivia
  quizzes" (III.2) and forbids combining Spotify with other services' streams (III.5). It *does* allow users to
  transfer their own data (III.9). So the user exports their playlists, and this app only reads that file.
- [Deezer's API](https://developers.deezer.com/termsofuse) gives free 30-second previews, but **for non-commercial
  use only** (no ads, no paid version), and audio must not be stored. Previews are fetched fresh for every round.
  Get Deezer's written OK before an App Store release; Apple may ask for it (Review Guideline 5.2.2).

## Setup

### 1. Export your playlists from Spotify

| Option | What you get | Notes |
|---|---|---|
| **[Exportify](https://exportify.net)** (recommended) | one `.csv` per playlist | Includes album release date and ISRC, so the year is better and Deezer matches are exact |
| Spotify **[Download your data](https://www.spotify.com/account/privacy/)** → "Account data" | `Playlist1.json` (all playlists), `YourLibrary.json` (Liked Songs) | Takes a few days. No years in the export, so the year comes from Deezer, which is often a compilation year |

### 2. Run the app

```bash
python3 -m venv .venv && source .venv/bin/activate     # see note below if venv/pip are missing
pip install -e ".[dev]"
python scripts/dev_server.py     # web app on port 8550, restarts on every code change
```

Open <http://localhost:8550>. For an iPhone-sized view press **F12 → Ctrl+Shift+M** and choose an iPhone.
After a code change the dev server restarts by itself; just press **F5** in the browser.
(`flet run -d -r --web` can't restart while a browser tab is connected, hence the small runner script.)
`flet run src/main.py` (without `--web`) opens a desktop window instead.

### 3. First game

1. Click **Import** and choose one or more exported files. Re-importing a playlist with the same name replaces it.
2. Choose the playlist, then **Start**. The preview plays right away; **Replay snippet** plays it again.
3. Songs Deezer has no preview for are skipped automatically (the status line counts them).

Tests: `pytest`, or with no extra packages: `python3 -m unittest discover -s tests`

> **No `python3-venv` / pip on Debian?** `python3 -m venv --without-pip .venv`, then download
> <https://bootstrap.pypa.io/get-pip.py> and run `.venv/bin/python get-pip.py`.

### Building for mobile

```bash
flet build ipa   # iOS – needs macOS + Xcode + Apple developer account
flet build apk   # Android
```

Flet 0.28's `ft.Audio` is deprecated; when upgrading Flet, switch to the `flet-audio` package.

## Project layout

```
src/
  main.py                    # Flet entry point
  music_guessr/
    app.py                   # app shell + bottom navigation
    game.py                  # scoring & rounds
    matching.py              # fuzzy guess matching
    importer.py              # Exportify CSV + Spotify data export (JSON) import
    deezer.py                # preview lookup (ISRC, then scored search), covers, artist pictures
    wikipedia.py             # Wikidata (Spotify IDs) + Wikipedia search
    images.py                # artist photos: Deezer, Wikipedia as fallback
    storage.py               # SQLite: playlists, Deezer matches, rounds, guessed songs and artists
    stats.py                 # statistics computations
    views/                   # play, lists (songs/artists), stats screens
tests/
```

### How Wikipedia links are found

1. **Exact:** Wikidata stores Spotify IDs (`P1902` artist, `P2207` track); the IDs come from your export file.
   One SPARQL query maps them to articles.
2. **Fallback:** Wikipedia search, accepted only when the article title matches the name. No link is better than a
   wrong one.

### Scoring

| | points |
|---|---|
| correct artist (any credited artist) | 1 |
| correct title | 1 |
| exact year / within ±2 years | 2 / 1 |

## TODO

- [ ] Original release year via MusicBrainz (Deezer and Spotify dates are often remaster/compilation years)
- [ ] Ask Deezer for written approval before any public release
- [ ] "Preview by Deezer" branding per Deezer's trademark guidelines
- [ ] Achievements / badges on the stats page
- [ ] Optional multiple-choice mode
- [ ] Localised UI (DE/EN) and Wikipedia language setting in the UI
