from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Artist:
    id: str
    name: str


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artists: tuple[Artist, ...]
    year: int | None
    uri: str
    album: str = ""
    image_url: str | None = None
    duration_ms: int = 0

    @property
    def artist_names(self) -> str:
        return ", ".join(a.name for a in self.artists)


@dataclass
class RoundResult:
    artist_ok: bool
    title_ok: bool
    year_diff: int | None  # None = no year guessed or year unknown
    points: int
    matched_artists: list[Artist] = field(default_factory=list)

    @property
    def year_exact(self) -> bool:
        return self.year_diff == 0

    @property
    def perfect(self) -> bool:
        return self.artist_ok and self.title_ok and self.year_exact
