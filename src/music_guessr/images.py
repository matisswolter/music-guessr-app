"""Artist pictures: Spotify artist image first, Wikipedia lead image as fallback.

Song covers need no lookup – the album cover URL comes with every Spotify track.
"""

from __future__ import annotations

from . import wikipedia
from .http import HTTPError


def fill_artist_images(storage, spotify=None) -> int:
    found = 0
    for a in storage.artists_missing_image():
        url = None
        if spotify is not None:
            try:
                url = spotify.artist_image(a["artist_id"])
            except (HTTPError, OSError, RuntimeError):
                url = None
        if url is None and a["wiki_url"]:
            url = wikipedia.thumbnail(a["wiki_url"])
        if url is None and not a["wiki_checked"]:
            continue  # wait until the Wikipedia link lookup has run, then retry
        storage.set_artist_image(a["artist_id"], url)
        found += url is not None
    return found
