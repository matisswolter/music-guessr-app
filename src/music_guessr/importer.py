"""Import playlists that the user exported from Spotify themselves.

Supported files
---------------
* Exportify CSV (https://exportify.net) – one playlist per file, name taken from the file name.
  Column titles are translated by Exportify, so columns are read by position.
* Spotify "Download your data" export: ``Playlist1.json`` (all playlists) and
  ``YourLibrary.json`` (Liked Songs).

The app never talks to the Spotify API; the user transfers their own data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import PurePath

from .matching import normalize
from .models import Artist, Track

# Exportify base columns (fixed order, translated titles)
COL_TRACK_URI, COL_TRACK_NAME, COL_ARTIST_URIS, COL_ARTIST_NAMES = 0, 1, 2, 3
COL_ALBUM_NAME, COL_RELEASE_DATE, COL_DURATION, COL_ISRC = 5, 8, 12, 16


@dataclass
class ImportedPlaylist:
    name: str
    tracks: list[Track]
    source: str


class ImportError_(ValueError):
    """Raised for files we can't understand (message is shown to the user)."""


def _spotify_id(uri: str) -> str | None:
    m = re.fullmatch(r"spotify:(?:track|artist):([A-Za-z0-9]{22})", (uri or "").strip())
    return m.group(1) if m else None


def _fallback_id(title: str, artists: str) -> str:
    return "x" + hashlib.sha1(f"{normalize(title)}|{normalize(artists)}".encode()).hexdigest()[:21]


def _year(date: str) -> int | None:
    return int(date[:4]) if (date or "")[:4].isdigit() else None


def _artist(name: str, uri: str = "") -> Artist:
    sid = _spotify_id(uri)
    return Artist(id=sid or "name:" + normalize(name), name=name)


def _split_artists(names: str) -> list[str]:
    # Exportify joins with ", " and escapes commas inside names as "\,"
    return [n.replace("\\,", ",").strip() for n in re.split(r"(?<!\\), ", names or "") if n.strip()]


def _make_track(title: str, artists: list[Artist], uri: str = "", album: str = "", date: str = "",
                duration: str | int = 0, isrc: str = "") -> Track | None:
    title = (title or "").strip()
    if not title or not artists:
        return None
    names = ", ".join(a.name for a in artists)
    return Track(
        id=_spotify_id(uri) or _fallback_id(title, names),
        title=title,
        artists=tuple(artists),
        year=_year(date),
        uri=uri or "",
        album=album or "",
        duration_ms=int(duration) if str(duration).isdigit() else 0,
        isrc=(isrc or "").strip().upper() or None,
    )


def parse_exportify_csv(text: str, playlist_name: str) -> ImportedPlaylist:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if len(rows) < 1 or len(rows[0]) < 4:
        raise ImportError_("This CSV doesn't look like an Exportify export.")
    tracks = []
    for row in rows[1:]:
        if len(row) <= COL_ARTIST_NAMES or not row[COL_TRACK_URI].startswith("spotify:track:"):
            continue  # local files, podcast episodes, empty lines
        names = _split_artists(row[COL_ARTIST_NAMES])
        uris = [u.strip() for u in row[COL_ARTIST_URIS].split(",")]
        artists = [_artist(n, uris[i] if i < len(uris) else "") for i, n in enumerate(names)]
        get = lambda col: row[col] if len(row) > col else ""  # noqa: E731
        t = _make_track(row[COL_TRACK_NAME], artists, row[COL_TRACK_URI], get(COL_ALBUM_NAME),
                        get(COL_RELEASE_DATE), get(COL_DURATION), get(COL_ISRC))
        if t:
            tracks.append(t)
    if not tracks:
        raise ImportError_("No songs found in this CSV.")
    return ImportedPlaylist(playlist_name, tracks, "exportify")


def parse_spotify_data_export(data: dict) -> list[ImportedPlaylist]:
    result = []
    for pl in data.get("playlists", []):  # Playlist1.json
        tracks = []
        for item in pl.get("items", []):
            t = item.get("track") or {}
            track = _make_track(t.get("trackName", ""), [_artist(t.get("artistName", ""))] if t.get("artistName") else [],
                                t.get("trackUri", ""), t.get("albumName", ""))
            if track:
                tracks.append(track)
        if tracks:
            result.append(ImportedPlaylist(pl.get("name") or "Playlist", tracks, "spotify-data"))
    if data.get("tracks"):  # YourLibrary.json
        tracks = [t for t in (_make_track(x.get("track", ""), [_artist(x["artist"])] if x.get("artist") else [],
                                          x.get("uri", ""), x.get("album", ""))
                              for x in data["tracks"]) if t]
        if tracks:
            result.append(ImportedPlaylist("❤ Liked Songs", tracks, "spotify-data"))
    if not result:
        raise ImportError_("No playlists found. Use Playlist1.json or YourLibrary.json from Spotify's data export.")
    return result


def parse_file(file_name: str, content: bytes) -> list[ImportedPlaylist]:
    text = content.decode("utf-8-sig", errors="replace")
    suffix = PurePath(file_name).suffix.lower()
    if suffix == ".csv":
        name = PurePath(file_name).stem.replace("_", " ").strip() or "Playlist"
        return [parse_exportify_csv(text, name)]
    if suffix == ".json":
        try:
            return parse_spotify_data_export(json.loads(text))
        except json.JSONDecodeError as e:
            raise ImportError_(f"Invalid JSON file: {e}") from None
    raise ImportError_("Please choose an Exportify .csv or a Spotify data export .json file.")
