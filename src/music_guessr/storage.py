"""SQLite persistence: imported playlists, Deezer matches, rounds, guessed songs and artists."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Artist, RoundResult, Track

_SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    track_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artists TEXT NOT NULL,          -- JSON [[id, name], ...]
    album TEXT,
    year INTEGER,
    isrc TEXT,
    duration_ms INTEGER,
    uri TEXT,
    PRIMARY KEY (playlist_id, position)
);
-- Deezer match per track (IDs and cover only - never audio). deezer_id NULL = no preview found.
CREATE TABLE IF NOT EXISTS deezer_matches (
    track_id TEXT PRIMARY KEY,
    deezer_id INTEGER,
    cover_url TEXT,
    link TEXT,
    release_date TEXT,
    checked_at TEXT NOT NULL
);
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
        self.conn.execute("PRAGMA foreign_keys = ON")
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

    # --- imported playlists -----------------------------------------------------
    def save_playlist(self, name: str, tracks: list[Track], source: str) -> str:
        """Store an imported playlist; re-importing a playlist with the same name replaces it."""
        with self.conn:
            old = self.conn.execute("SELECT id FROM playlists WHERE name = ?", (name,)).fetchone()
            pid = old["id"] if old else uuid.uuid4().hex
            self.conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (pid,))
            self.conn.execute("INSERT OR REPLACE INTO playlists (id, name, source, imported_at) VALUES (?,?,?,?)",
                              (pid, name, source, _now()))
            self.conn.executemany(
                "INSERT INTO playlist_tracks (playlist_id, position, track_id, title, artists, album, year, isrc,"
                " duration_ms, uri) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(pid, i, t.id, t.title, json.dumps([[a.id, a.name] for a in t.artists]), t.album, t.year, t.isrc,
                  t.duration_ms, t.uri) for i, t in enumerate(tracks)],
            )
        return pid

    def playlists(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT p.*, COUNT(t.position) AS size FROM playlists p LEFT JOIN playlist_tracks t"
            " ON t.playlist_id = p.id GROUP BY p.id ORDER BY p.name COLLATE NOCASE")]

    def delete_playlist(self, playlist_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))

    def playlist_tracks(self, playlist_id: str) -> list[Track]:
        rows = self.conn.execute("SELECT * FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                                 (playlist_id,))
        return [Track(id=r["track_id"], title=r["title"],
                      artists=tuple(Artist(i, n) for i, n in json.loads(r["artists"])),
                      year=r["year"], uri=r["uri"] or "", album=r["album"] or "",
                      duration_ms=r["duration_ms"] or 0, isrc=r["isrc"]) for r in rows]

    # --- Deezer matches ----------------------------------------------------------
    def deezer_match(self, track_id: str) -> dict | None:
        """Cached match row, or None if this track was never looked up."""
        r = self.conn.execute("SELECT * FROM deezer_matches WHERE track_id = ?", (track_id,)).fetchone()
        return dict(r) if r else None

    def set_deezer_match(self, track_id: str, match) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO deezer_matches (track_id, deezer_id, cover_url, link, release_date, checked_at)"
                " VALUES (?,?,?,?,?,?)",
                (track_id, match.deezer_id if match else None, match.cover_url if match else None,
                 match.link if match else None, match.release_date if match else None, _now()),
            )

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
