"""Forgiving comparison of user guesses with Spotify metadata."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_SUFFIX_KEYWORDS = re.compile(
    r"remaster|remix|live|mono|stereo|edit|version|mix|demo|acoustic|bonus|deluxe|anniversary|from|recorded",
    re.IGNORECASE,
)
_BRACKET_KEYWORDS = re.compile(rf"feat\.?|ft\.|\bwith\b|{_SUFFIX_KEYWORDS.pattern}", re.IGNORECASE)
_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")


def clean_title(title: str) -> str:
    """Strip Spotify noise such as ' - Remastered 2009', '(feat. X)' or '[Live]'."""
    if " - " in title:
        head, tail = title.split(" - ", 1)
        if _SUFFIX_KEYWORDS.search(tail):
            title = head
    title = _BRACKETS.sub(lambda m: "" if _BRACKET_KEYWORDS.search(m.group()) else m.group(), title)
    return title.strip() or title


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^the ", "", text)
    return text


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def is_match(guess: str, answer: str, threshold: float = 0.85) -> bool:
    g, a = normalize(guess), normalize(answer)
    if not g or not a:
        return False
    if g == a:
        return True
    # Short answers (e.g. "U2", "Yes") must be typed exactly.
    if len(a) <= 3:
        return False
    return SequenceMatcher(None, g, a).ratio() >= threshold


def title_matches(guess: str, title: str) -> bool:
    return is_match(guess, title) or is_match(guess, clean_title(title))
