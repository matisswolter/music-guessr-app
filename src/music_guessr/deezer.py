"""Deezer public API: find a song's 30-second preview, cover and artist picture.

No account or key is needed. Per Deezer's terms, audio is never stored – the
(time-limited) preview URL is fetched fresh right before playing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .http import HTTPError, request
from .matching import clean_title, normalize, similarity
from .models import Track

API = "https://api.deezer.com"


@dataclass
class DeezerMatch:
    deezer_id: int
    cover_url: str | None
    link: str
    release_date: str | None = None


def _get(path: str, **params) -> dict:
    data = request("GET", API + path, params=params or None) or {}
    if isinstance(data, dict) and data.get("error"):
        raise HTTPError(400, str(data["error"]))
    return data


def _usable(t: dict) -> bool:
    return bool(t.get("readable", True) and t.get("preview"))


def _to_match(t: dict) -> DeezerMatch:
    album = t.get("album") or {}
    return DeezerMatch(
        deezer_id=int(t["id"]),
        cover_url=album.get("cover_big") or album.get("cover_medium"),
        link=t.get("link") or f"https://www.deezer.com/track/{t['id']}",
        release_date=t.get("release_date") or album.get("release_date"),
    )


_VERSION_WORDS = re.compile(r"\b(live|remix|mix|karaoke|instrumental|acoustic|cover|tribute|demo|edit|version|"
                            r"sped up|slowed|nightcore|8-bit|lullaby)\b", re.IGNORECASE)


def _score(candidate: dict, track: Track) -> float:
    cand_title = candidate.get("title", "")
    title = similarity(clean_title(cand_title), clean_title(track.title))
    artist_names = [a.name for a in track.artists]
    artist = max(similarity(candidate.get("artist", {}).get("name", ""), n) for n in artist_names)
    # Prefer the original recording: penalise live/remix/karaoke/... versions the playlist didn't ask for.
    unwanted = set(w.lower() for w in _VERSION_WORDS.findall(cand_title)) - \
        set(w.lower() for w in _VERSION_WORDS.findall(track.title))
    return 0.6 * title + 0.4 * artist - 0.15 * len(unwanted)


def find(track: Track) -> DeezerMatch | None:
    """Best playable Deezer version of a track: exact ISRC first, then a scored search."""
    if track.isrc:
        try:
            t = _get(f"/track/isrc:{track.isrc}")
            if _usable(t):
                return _to_match(t)
        except (HTTPError, OSError):
            pass

    main_artist = track.artists[0].name if track.artists else ""
    title = clean_title(track.title)
    candidates: list[dict] = []
    for q in (f'artist:"{main_artist}" track:"{title}"', f"{main_artist} {title}"):
        try:
            candidates = [c for c in _get("/search", q=q, limit=10).get("data", []) if _usable(c)]
        except (HTTPError, OSError):
            candidates = []
        if candidates:
            break
    if not candidates:
        return None
    best = max(candidates, key=lambda c: _score(c, track))
    if _score(best, track) < 0.75:
        return None
    match = _to_match(best)
    album_id = (best.get("album") or {}).get("id")
    if track.year is None and not match.release_date and album_id:
        # Search results carry no date; the album does (Spotify's data export has no years at all).
        try:
            match.release_date = _get(f"/album/{album_id}").get("release_date")
        except (HTTPError, OSError):
            pass
    return match


def preview_url(deezer_id: int) -> str | None:
    """Fresh, signed preview URL (they expire, so don't cache them)."""
    try:
        t = _get(f"/track/{deezer_id}")
    except (HTTPError, OSError):
        return None
    return t.get("preview") or None


def artist_picture(name: str) -> str | None:
    try:
        hits = _get("/search/artist", q=name, limit=5).get("data", [])
    except (HTTPError, OSError):
        return None
    for a in hits:
        if normalize(a.get("name", "")) == normalize(name):
            return a.get("picture_big") or a.get("picture_medium")
    return None
