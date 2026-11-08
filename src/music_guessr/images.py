"""Artist pictures: Deezer artist picture first, Wikipedia lead image as fallback.

Song covers come from the Deezer match of each track.
"""

from __future__ import annotations

from typing import Callable

from . import deezer, wikipedia


def fill_artist_images(storage, picture_lookup: Callable[[str], str | None] | None = deezer.artist_picture) -> int:
    found = 0
    for a in storage.artists_missing_image():
        url = None
        if picture_lookup is not None:
            try:
                url = picture_lookup(a["name"])
            except OSError:
                url = None
        if url is None and a["wiki_url"]:
            url = wikipedia.thumbnail(a["wiki_url"])
        if url is None and not a["wiki_checked"]:
            continue  # wait until the Wikipedia link lookup has run, then retry
        storage.set_artist_image(a["artist_id"], url)
        found += url is not None
    return found
