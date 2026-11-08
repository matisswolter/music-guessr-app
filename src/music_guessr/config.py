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

# Wikipedia language edition used for links ("en", "de", ...).
WIKIPEDIA_LANG = os.getenv("MUSIC_GUESSR_WIKI_LANG", "en")

# Wikimedia asks API clients to send a descriptive User-Agent.
USER_AGENT = "MusicGuessr/0.1 (https://github.com/matisswolter/music-guessr-app)"


def data_dir() -> Path:
    """Directory for the database and settings (Flet sets FLET_APP_STORAGE_DATA in built apps)."""
    base = os.getenv("FLET_APP_STORAGE_DATA") or str(Path.home() / ".music_guessr")
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_dir() -> Path:
    """Where the web version receives imported files (deleted right after import)."""
    path = data_dir() / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path
