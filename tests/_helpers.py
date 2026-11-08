import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from music_guessr.models import Artist, Track  # noqa: E402


def make_track(id="t1", title="Bohemian Rhapsody - Remastered 2011", artists=(("a1", "Queen"),), year=1975):
    return Track(id=id, title=title, artists=tuple(Artist(i, n) for i, n in artists), year=year,
                 uri=f"spotify:track:{id}", duration_ms=354_000)
