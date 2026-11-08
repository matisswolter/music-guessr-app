import json
import random
import tempfile
import time
import unittest
from pathlib import Path

import _helpers  # noqa: F401
from music_guessr.spotify import LIKED_SONGS, SCOPES, SpotifyAuth, SpotifyClient


def auth_with_scopes(scopes: str) -> SpotifyAuth:
    f = Path(tempfile.mkdtemp()) / "token.json"
    f.write_text(json.dumps({"access_token": "x", "refresh_token": "y", "scope": scopes,
                             "expires_at": time.time() + 3600}))
    return SpotifyAuth("cid", "http://127.0.0.1:8888/callback", f)


def fake_track(i):
    return {"id": f"t{i}", "name": f"Song {i}", "uri": f"spotify:track:t{i}", "type": "track",
            "artists": [{"id": "a", "name": "Artist"}], "album": {"release_date": "1999-01-01", "images": []}}


class FakeLibrary(SpotifyClient):
    def __init__(self, total):
        super().__init__(auth_with_scopes(SCOPES))
        self.total, self.offsets = total, []

    def _call(self, method, path, **kw):
        assert path == "/me/tracks"
        p = kw["params"]
        if p["limit"] == 1:
            return {"total": self.total, "items": []}
        self.offsets.append(p["offset"])
        end = min(p["offset"] + p["limit"], self.total)
        return {"items": [{"track": fake_track(i)} for i in range(p["offset"], end)]}


class TestScopes(unittest.TestCase):
    def test_old_login_without_library_scope_must_log_in_again(self):
        old = auth_with_scopes("playlist-read-private playlist-read-collaborative "
                               "user-read-playback-state user-modify-playback-state")
        self.assertFalse(old.logged_in)
        self.assertEqual(old.missing_scopes, {"user-library-read"})
        self.assertTrue(auth_with_scopes(SCOPES).logged_in)


class TestLikedSongs(unittest.TestCase):
    def test_small_library_loads_completely(self):
        sp = FakeLibrary(120)
        self.assertEqual(len(sp.playlist_tracks(LIKED_SONGS)), 120)
        self.assertEqual(sp.offsets, [0, 50, 100])

    def test_big_library_is_sampled(self):
        sp = FakeLibrary(3000)
        tracks = sp.liked_tracks(max_tracks=500, rng=random.Random(1))
        self.assertEqual(len(tracks), 500)
        self.assertEqual(len(sp.offsets), 10)
        self.assertEqual(len(set(t.id for t in tracks)), 500)


if __name__ == "__main__":
    unittest.main()
