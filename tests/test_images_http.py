import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from _helpers import make_track
from music_guessr import images
from music_guessr.game import evaluate
from music_guessr.storage import Storage


def fake_deezer_picture(name):
    return {"Queen": "https://e-cdns-images.dzcdn.net/queen.jpg"}.get(name)


class TestArtistImages(unittest.TestCase):
    def test_deezer_picture_then_wikipedia_fallback(self):
        db = Storage(":memory:")
        t = make_track(artists=(("a1", "Queen"), ("a2", "David Bowie")))
        db.record_round(t, evaluate(t, "queen, david bowie", "", None))
        original = images.wikipedia.thumbnail
        self.addCleanup(setattr, images.wikipedia, "thumbnail", original)
        images.wikipedia.thumbnail = lambda url: "https://upload.wikimedia.org/bowie.jpg"

        # a2 has no Spotify image and no wiki lookup yet -> postponed
        self.assertEqual(images.fill_artist_images(db, fake_deezer_picture), 1)
        self.assertEqual([a["name"] for a in db.artists_missing_image()], ["David Bowie"])

        db.set_artist_wiki("a2", "https://en.wikipedia.org/wiki/David_Bowie")
        self.assertEqual(images.fill_artist_images(db, fake_deezer_picture), 1)
        pics = {a["name"]: a["image_url"] for a in db.guessed_artists()}
        self.assertEqual(pics, {"Queen": "https://e-cdns-images.dzcdn.net/queen.jpg",
                                "David Bowie": "https://upload.wikimedia.org/bowie.jpg"})

    def test_migrates_old_database(self):
        path = Path(tempfile.mkdtemp()) / "old.sqlite3"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE guessed_artists (artist_id TEXT PRIMARY KEY, name TEXT NOT NULL, wiki_url TEXT,"
                    " wiki_checked INTEGER NOT NULL DEFAULT 0, first_guessed_at TEXT NOT NULL,"
                    " times_guessed INTEGER NOT NULL DEFAULT 1)")
        con.execute("INSERT INTO guessed_artists (artist_id, name, first_guessed_at) VALUES ('a1','Queen','x')")
        con.commit(); con.close()
        db = Storage(path)
        self.assertEqual(db.artists_missing_image()[0]["image_url"], None)


class TestHttpNonJson(unittest.TestCase):
    def test_non_json_body_is_tolerated(self):
        import http.server
        from music_guessr.http import request

        class H(http.server.BaseHTTPRequestHandler):
            def do_PUT(self):  # noqa: N802
                self.send_response(200); self.end_headers(); self.wfile.write(b"ok, paused")
            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        self.assertIsNone(request("PUT", f"http://127.0.0.1:{srv.server_port}/me/player/pause"))
        srv.server_close()


if __name__ == "__main__":
    unittest.main()
