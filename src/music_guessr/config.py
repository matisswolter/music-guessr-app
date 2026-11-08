"""App configuration. Values can be overridden with environment variables."""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Read KEY=value lines from a .env file in the project root (dev convenience, never committed)."""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# Create an app at https://developer.spotify.com/dashboard and paste its Client ID here
# (or set SPOTIFY_CLIENT_ID). With the PKCE flow no client secret is needed in the app.
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")

# Must be registered *exactly* like this in the Spotify dashboard.
# Loopback redirect for desktop development; mobile builds will need a custom URL scheme.
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# Wikipedia language edition used for links ("en", "de", ...).
WIKIPEDIA_LANG = os.getenv("MUSIC_GUESSR_WIKI_LANG", "en")

# Wikimedia asks API clients to send a descriptive User-Agent.
USER_AGENT = "MusicGuessr/0.1 (https://github.com/matisswolter/music-guessr-app)"


def data_dir() -> Path:
    """Directory for the database and tokens (Flet sets FLET_APP_STORAGE_DATA in built apps)."""
    base = os.getenv("FLET_APP_STORAGE_DATA") or str(Path.home() / ".music_guessr")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path
