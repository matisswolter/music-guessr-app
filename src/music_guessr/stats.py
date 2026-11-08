"""Derive statistics for the stats page from the stored rounds."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class Stats:
    rounds: int = 0
    points: int = 0
    artist_rate: float = 0.0
    title_rate: float = 0.0
    year_exact_rate: float = 0.0
    year_close_rate: float = 0.0
    avg_year_error: float | None = None
    perfect_rounds: int = 0
    best_streak: int = 0
    current_streak: int = 0
    cumulative_points: list[tuple[int, int]] = field(default_factory=list)  # (round number, total points)
    points_per_day: list[tuple[str, int]] = field(default_factory=list)
    decade_accuracy: list[tuple[str, float, int]] = field(default_factory=list)  # (decade, title rate, rounds)
    top_artists: list[tuple[str, int]] = field(default_factory=list)


def _streak_hit(r: dict) -> bool:
    """A round continues the streak when both artist and title were right."""
    return bool(r["artist_ok"]) and bool(r["title_ok"])


def compute(rounds: list[dict], top_n: int = 5) -> Stats:
    s = Stats(rounds=len(rounds))
    if not rounds:
        return s

    n = len(rounds)
    s.points = sum(r["points"] for r in rounds)
    s.artist_rate = sum(bool(r["artist_ok"]) for r in rounds) / n
    s.title_rate = sum(bool(r["title_ok"]) for r in rounds) / n

    year_rounds = [r for r in rounds if r["year_diff"] is not None]
    if year_rounds:
        s.year_exact_rate = sum(r["year_diff"] == 0 for r in year_rounds) / len(year_rounds)
        s.year_close_rate = sum(r["year_diff"] <= 2 for r in year_rounds) / len(year_rounds)
        s.avg_year_error = sum(r["year_diff"] for r in year_rounds) / len(year_rounds)

    s.perfect_rounds = sum(_streak_hit(r) and r["year_diff"] == 0 for r in rounds)

    streak = 0
    total = 0
    per_day: dict[str, int] = defaultdict(int)
    for i, r in enumerate(rounds, start=1):
        streak = streak + 1 if _streak_hit(r) else 0
        s.best_streak = max(s.best_streak, streak)
        total += r["points"]
        s.cumulative_points.append((i, total))
        per_day[str(r["played_at"])[:10]] += r["points"]
    s.current_streak = streak
    s.points_per_day = sorted(per_day.items())

    by_decade: dict[int, list[dict]] = defaultdict(list)
    for r in rounds:
        if r["year"]:
            by_decade[(int(r["year"]) // 10) * 10].append(r)
    s.decade_accuracy = [
        (f"{d}s", sum(bool(x["title_ok"]) for x in rs) / len(rs), len(rs)) for d, rs in sorted(by_decade.items())
    ]

    artists = Counter()
    for r in rounds:
        if r["artist_ok"]:
            artists[r["artists"].split(", ")[0]] += 1
    s.top_artists = artists.most_common(top_n)
    return s
