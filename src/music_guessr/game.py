"""Game rules: scoring a single round and drawing tracks from a playlist."""

from __future__ import annotations

import random

from .matching import is_match, title_matches
from .models import RoundResult, Track

POINTS_ARTIST = 1
POINTS_TITLE = 1
POINTS_YEAR_EXACT = 2
POINTS_YEAR_CLOSE = 1
YEAR_CLOSE_RANGE = 2


def evaluate(track: Track, guess_artist: str, guess_title: str, guess_year: str | int | None) -> RoundResult:
    # Any credited artist counts; several comma-separated names may be guessed at once.
    guessed_names = [g for g in str(guess_artist or "").split(",") if g.strip()]
    matched = [a for a in track.artists if any(is_match(g, a.name) for g in guessed_names)]
    artist_ok = bool(matched)
    title_ok = title_matches(guess_title or "", track.title)

    year_diff: int | None = None
    try:
        if guess_year not in (None, "") and track.year is not None:
            year_diff = abs(int(guess_year) - track.year)
    except (TypeError, ValueError):
        year_diff = None

    points = (POINTS_ARTIST if artist_ok else 0) + (POINTS_TITLE if title_ok else 0)
    if year_diff == 0:
        points += POINTS_YEAR_EXACT
    elif year_diff is not None and year_diff <= YEAR_CLOSE_RANGE:
        points += POINTS_YEAR_CLOSE

    return RoundResult(artist_ok, title_ok, year_diff, points, matched)


class GameSession:
    """Plays through a shuffled list of tracks, one round per track."""

    def __init__(self, tracks: list[Track], skip_ids: set[str] | None = None, rng: random.Random | None = None):
        self._rng = rng or random.Random()
        pool = [t for t in tracks if t.id not in (skip_ids or set())] or list(tracks)
        self._rng.shuffle(pool)
        self._queue = pool
        self.current: Track | None = None
        self.score = 0
        self.rounds = 0

    @property
    def remaining(self) -> int:
        return len(self._queue)

    def next_track(self) -> Track | None:
        self.current = self._queue.pop() if self._queue else None
        return self.current

    def snippet_start_ms(self, track: Track) -> int:
        """Random start somewhere in the middle so the intro doesn't give it away."""
        if track.duration_ms < 60_000:
            return 0
        return self._rng.randint(int(track.duration_ms * 0.2), int(track.duration_ms * 0.6))

    def submit(self, guess_artist: str, guess_title: str, guess_year: str | int | None) -> RoundResult:
        if self.current is None:
            raise RuntimeError("No active round – call next_track() first")
        result = evaluate(self.current, guess_artist, guess_title, guess_year)
        self.score += result.points
        self.rounds += 1
        return result
