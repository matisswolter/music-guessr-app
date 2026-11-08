"""SQLite persistence for rounds, guessed songs and guessed artists."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import RoundResult, Track

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at TEXT NOT NULL,
    playlist_id TEXT,
    track_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,
    year INTEGER,
    artist_ok INTEGER NOT NULL,
    title_ok INTEGER NOT NULL,
    year_diff INTEGER,
    points INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS guessed_songs (
    track_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,
    year INTEGER,
    image_url TEXT,
    wiki_url TEXT,
    wiki_checked INTEGER NOT NULL DEFAULT 0,
    first_guessed_at TEXT NOT NULL,
    times_guessed INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS guessed_artists (
    artist_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    image_url TEXT,
    image_checked INTEGER NOT NULL DEFAULT 0,
    wiki_url TEXT,
    wiki_checked INTEGER NOT NULL DEFAULT 0,
    first_guessed_at TEXT NOT NULL,
    times_guessed INTEGER NOT NULL DEFAULT 1
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: Path | str):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after the first release to existing databases."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(guessed_artists)")}
        with self.conn:
            if "image_url" not in cols:
                self.conn.execute("ALTER TABLE guessed_artists ADD COLUMN image_url TEXT")
            if "image_checked" not in cols:
                self.conn.execute("ALTER TABLE guessed_artists ADD COLUMN image_checked INTEGER NOT NULL DEFAULT 0")

    def record_round(self, track: Track, result: RoundResult, playlist_id: str | None = None,
                     played_at: str | None = None) -> None:
        ts = played_at or _now()
        with self.conn:
            self.conn.execute(
                "INSERT INTO rounds (played_at, playlist_id, track_id, title, artists, year, artist_ok, title_ok,"
                " year_diff, points) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, playlist_id, track.id, track.title, track.artist_names, track.year,
                 int(result.artist_ok), int(result.title_ok), result.year_diff, result.points),
            )
            if result.title_ok:
                self.conn.execute(
                    "INSERT INTO guessed_songs (track_id, title, artists, year, image_url, first_guessed_at)"
                    " VALUES (?,?,?,?,?,?) ON CONFLICT(track_id) DO UPDATE SET times_guessed = times_guessed + 1",
                    (track.id, track.title, track.artist_names, track.year, track.image_url, ts),
                )
            for artist in result.matched_artists:
                self.conn.execute(
                    "INSERT INTO guessed_artists (artist_id, name, first_guessed_at) VALUES (?,?,?)"
                    " ON CONFLICT(artist_id) DO UPDATE SET times_guessed = times_guessed + 1",
                    (artist.id, artist.name, ts),
                )

    def rounds(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM rounds ORDER BY played_at, id")]

    def guessed_songs(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM guessed_songs ORDER BY title COLLATE NOCASE")]

    def guessed_artists(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM guessed_artists ORDER BY name COLLATE NOCASE")]

    def guessed_track_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT track_id FROM guessed_songs")}

    # --- Wikipedia link cache -------------------------------------------------
    def songs_missing_wiki(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM guessed_songs WHERE wiki_checked = 0")]

    def artists_missing_wiki(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM guessed_artists WHERE wiki_checked = 0")]

    def artists_missing_image(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM guessed_artists WHERE image_checked = 0")]

    def set_artist_image(self, artist_id: str, url: str | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE guessed_artists SET image_url = ?, image_checked = 1 WHERE artist_id = ?",
                              (url, artist_id))

    def set_song_wiki(self, track_id: str, url: str | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE guessed_songs SET wiki_url = ?, wiki_checked = 1 WHERE track_id = ?",
                              (url, track_id))

    def set_artist_wiki(self, artist_id: str, url: str | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE guessed_artists SET wiki_url = ?, wiki_checked = 1 WHERE artist_id = ?",
                              (url, artist_id))
