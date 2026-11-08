# Music Guessr 🎵

Guess the **artist**, **title** and **release year** of songs from your own Spotify playlists.

- 🎧 Snippets play from a random point in the song through your Spotify app
- ✅ Fuzzy answer matching: `beatles` = *The Beatles*, `beyonce` = *Beyoncé*, *“– Remastered 2011”* is ignored
- 📚 Two collections: **guessed songs** and **guessed artists**, each linked to Wikipedia when an article exists
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

**Trade-off:** Flet can't call native SDKs such as the Spotify iOS SDK. That's why playback uses the Spotify
**Web API remote-control endpoints** (`PUT /me/player/play`), which tell the user's Spotify app what to play.
If you later need deeper native integration, the Flutter/Dart route stays open.

## Spotify caveats (important)

- **Spotify Premium + an open Spotify app** (phone, desktop or speaker) are needed for playback.
  Spotify removed 30-second `preview_url`s for new apps in late 2024.
- Spotify's app shows "now playing", so put the phone face-down or play on a speaker or another device 😉
- New Spotify apps start in **Development Mode**, which allows only a few allow-listed users, and Spotify has kept
  tightening those limits through 2025–2026. Read the current
  [Web API docs and quota rules](https://developer.spotify.com/documentation/web-api) before planning a public release.
- The release year comes from the album's `release_date`. For remasters and compilations that's the re-release
  year. A future improvement is to look up the original year on MusicBrainz.

## Setup

1. Create an app at <https://developer.spotify.com/dashboard>, enable **Web API**, and add the redirect URI
   `http://127.0.0.1:8888/callback`. Add your Spotify account(s) under *User Management*.
2. Install and run (desktop, for development):

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   export SPOTIFY_CLIENT_ID=<your client id>
   flet run src/main.py
   ```

3. Tests: `pytest`, or with no extra packages: `python3 -m unittest discover -s tests`

### Building for mobile

```bash
flet build ipa   # iOS – needs macOS + Xcode + Apple developer account
flet build apk   # Android
```

Before the mobile builds can log in, the login flow needs a custom URL-scheme redirect
(e.g. `musicguessr://callback`) instead of the loopback server. See the TODO list.

## Project layout

```
src/
  main.py                    # Flet entry point
  music_guessr/
    app.py                   # app shell + bottom navigation
    game.py                  # scoring & rounds
    matching.py              # fuzzy guess matching
    spotify.py               # OAuth PKCE, playlists, playback
    wikipedia.py             # Wikidata (Spotify IDs) + Wikipedia search
    storage.py               # SQLite: rounds, guessed songs, guessed artists
    stats.py                 # statistics computations
    views/                   # play, lists (songs/artists), stats screens
tests/
```

### How Wikipedia links are found

1. **Exact:** Wikidata stores Spotify IDs (`P1902` artist, `P2207` track). One SPARQL query maps them to articles.
2. **Fallback:** Wikipedia search, accepted only when the article title matches the name. No link is better than a
   wrong one.

### Scoring

| | points |
|---|---|
| correct artist (any credited artist) | 1 |
| correct title | 1 |
| exact year / within ±2 years | 2 / 1 |

## TODO

- [ ] Mobile OAuth redirect via custom URL scheme (deep link)
- [ ] Original release year via MusicBrainz
- [ ] Device picker for playback
- [ ] Achievements / badges on the stats page
- [ ] Optional multiple-choice mode
- [ ] Localised UI (DE/EN) and Wikipedia language setting in the UI
