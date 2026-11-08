"""Find Wikipedia articles for songs and artists.

1. Exact lookup through Wikidata, which stores Spotify IDs
   (P1902 = Spotify artist ID, P2207 = Spotify track ID).
2. Fallback: Wikipedia full-text search, accepted only if the article title
   clearly matches – a missing link is better than a wrong one.
"""

from __future__ import annotations

from .config import WIKIPEDIA_LANG
from .http import HTTPError, request
from .matching import clean_title, normalize

SPARQL_URL = "https://query.wikidata.org/sparql"
P_SPOTIFY_ARTIST = "P1902"
P_SPOTIFY_TRACK = "P2207"


def _article_url(title: str, lang: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"


def wikidata_lookup(spotify_ids: list[str], prop: str, lang: str = WIKIPEDIA_LANG) -> dict[str, str]:
    """Map Spotify IDs to Wikipedia article URLs (batched SPARQL query)."""
    found: dict[str, str] = {}
    for i in range(0, len(spotify_ids), 50):
        chunk = spotify_ids[i:i + 50]
        values = " ".join(f'"{sid}"' for sid in chunk if sid.isalnum())
        if not values:
            continue
        query = f"""
        SELECT ?sid ?article WHERE {{
          VALUES ?sid {{ {values} }}
          ?item wdt:{prop} ?sid .
          ?article schema:about ?item ; schema:isPartOf <https://{lang}.wikipedia.org/> .
        }}"""
        try:
            data = request("GET", SPARQL_URL, params={"query": query, "format": "json"})
        except (HTTPError, OSError):
            continue
        for row in data["results"]["bindings"]:
            found.setdefault(row["sid"]["value"], row["article"]["value"])
    return found


def _search(query: str, lang: str) -> list[str]:
    data = request("GET", f"https://{lang}.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": query, "srlimit": 5, "format": "json",
    })
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def search_artist(name: str, lang: str = WIKIPEDIA_LANG) -> str | None:
    want = normalize(name)
    try:
        titles = _search(f"{name} music", lang)
    except (HTTPError, OSError):
        return None
    for t in titles:
        # "Queen (band)", "Adele", "Prince (musician)" ...
        if normalize(t.split(" (")[0]) == want:
            return _article_url(t, lang)
    return None


def search_song(title: str, artist: str, lang: str = WIKIPEDIA_LANG) -> str | None:
    want = normalize(clean_title(title))
    try:
        titles = _search(f'"{clean_title(title)}" {artist} song', lang)
    except (HTTPError, OSError):
        return None
    for t in titles:
        base = normalize(t.split(" (")[0])
        if base == want and ("song" in t.lower() or "(" not in t):
            return _article_url(t, lang)
    return None


def thumbnail(article_url: str) -> str | None:
    """Lead image of a Wikipedia article (used as artist photo fallback)."""
    try:
        host, title = article_url.split("/wiki/", 1)
        data = request("GET", f"{host}/api/rest_v1/page/summary/{title}")
    except (ValueError, HTTPError, OSError):
        return None
    return (data.get("thumbnail") or {}).get("source")


def fill_missing_links(storage) -> int:
    """Look up links for all guessed songs/artists not checked yet. Returns number of links found."""
    found = 0
    artists = storage.artists_missing_wiki()
    exact = wikidata_lookup([a["artist_id"] for a in artists], P_SPOTIFY_ARTIST)
    for a in artists:
        url = exact.get(a["artist_id"]) or search_artist(a["name"])
        storage.set_artist_wiki(a["artist_id"], url)
        found += url is not None

    songs = storage.songs_missing_wiki()
    exact = wikidata_lookup([s["track_id"] for s in songs], P_SPOTIFY_TRACK)
    for s in songs:
        url = exact.get(s["track_id"]) or search_song(s["title"], s["artists"].split(", ")[0])
        storage.set_song_wiki(s["track_id"], url)
        found += url is not None
    return found
