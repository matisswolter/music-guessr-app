import json
import unittest

from _helpers import make_track
from music_guessr import deezer, importer
from music_guessr.storage import Storage

EXPORTIFY_HEADER_DE = ('"Track-URI","Track-Name","Künstler-URI(s)","Künstlername(n)","Album-URI","Album-Name",'
                       '"Album-Künstler-URI(s)","Album-Künstlername(n)","Veröffentlichungsdatum des Albums",'
                       '"Album-Bild-URL","Disc-Nummer","Track-Nummer","Track-Dauer (ms)","Track-Vorschau-URL",'
                       '"Explizit","Popularität","ISRC","Hinzugefügt von","Hinzugefügt am"')
ROWS = [
    '"spotify:track:4u7EnebtmKWzUH433cf5Qv","Bohemian Rhapsody - Remastered 2011",'
    '"spotify:artist:1dfeR4HaWDbWqFHLkxsg1d","Queen","spotify:album:x","A Night at the Opera","","Queen",'
    '"1975-11-21","","1","11","354320","","false","80","GBUM71029604","",""',
    '"spotify:track:0aym2LBJBk9DAYuHHutrIl","Under Pressure","spotify:artist:1dfeR4HaWDbWqFHLkxsg1d, '
    'spotify:artist:0oSGxfWSnnOXhD2fKuz2Gy","Queen, David Bowie","","Hot Space","","Queen","1982","","1","11",'
    '"248000","","false","80","GBUM71029611","",""',
    '"spotify:track:5ChkMS8OtdzJeqyybCc9R5","Earth, Wind & Fire Tribute","spotify:artist:4QQgXkCYTt3BlENzhyNETg",'
    '"Earth\\, Wind & Fire","","Best of","","","1978-01-01","","1","1","200000","","false","50","","",""',
    '"spotify:local:::Demo:123","Local file","","Me","","","","","","","","","","","","","","",""',
]


class TestExportifyCsv(unittest.TestCase):
    def test_german_headers_escaped_commas_and_isrc(self):
        csv = "﻿" + EXPORTIFY_HEADER_DE + "\n" + "\n".join(ROWS) + "\n"
        [pl] = importer.parse_file("Oldie_but_Goldie.csv", csv.encode())
        self.assertEqual(pl.name, "Oldie but Goldie")
        self.assertEqual(len(pl.tracks), 3)  # local file skipped
        rhapsody, pressure, ewf = pl.tracks
        self.assertEqual((rhapsody.id, rhapsody.year, rhapsody.isrc, rhapsody.duration_ms),
                         ("4u7EnebtmKWzUH433cf5Qv", 1975, "GBUM71029604", 354320))
        self.assertEqual([(a.id, a.name) for a in pressure.artists],
                         [("1dfeR4HaWDbWqFHLkxsg1d", "Queen"), ("0oSGxfWSnnOXhD2fKuz2Gy", "David Bowie")])
        self.assertEqual([a.name for a in ewf.artists], ["Earth, Wind & Fire"])
        self.assertIsNone(ewf.isrc)

    def test_rejects_other_files(self):
        with self.assertRaises(importer.ImportError_):
            importer.parse_file("notes.txt", b"hello")
        with self.assertRaises(importer.ImportError_):
            importer.parse_file("empty.csv", b'"a","b","c","d"\n')


class TestSpotifyDataExport(unittest.TestCase):
    def test_playlists_and_liked_songs(self):
        playlists = {"playlists": [{"name": "WG Party", "items": [
            {"track": {"trackName": "Waterloo", "artistName": "ABBA", "albumName": "Waterloo",
                       "trackUri": "spotify:track:3Dy4REq8O09IlgiwuHQ3sk"}, "episode": None},
            {"track": None, "episode": {"episodeName": "Podcast"}},
        ]}, {"name": "Empty", "items": []}]}
        [pl] = importer.parse_file("Playlist1.json", json.dumps(playlists).encode())
        self.assertEqual((pl.name, len(pl.tracks), pl.tracks[0].id), ("WG Party", 1, "3Dy4REq8O09IlgiwuHQ3sk"))
        self.assertIsNone(pl.tracks[0].year)
        self.assertEqual(pl.tracks[0].artists[0].id, "name:abba")

        library = {"tracks": [{"artist": "Adele", "album": "21", "track": "Rolling in the Deep",
                               "uri": "spotify:track:1c8gk2PeTE04A1pIDH9YMk"}]}
        [liked] = importer.parse_file("YourLibrary.json", json.dumps(library).encode())
        self.assertEqual((liked.name, liked.tracks[0].title), ("❤ Liked Songs", "Rolling in the Deep"))


class TestPlaylistStorage(unittest.TestCase):
    def test_save_replace_load_delete(self):
        db = Storage(":memory:")
        t1, t2 = make_track(id="t1"), make_track(id="t2", title="Waterloo", artists=(("a2", "ABBA"),))
        pid = db.save_playlist("Mix", [t1, t2], "exportify")
        self.assertEqual(db.save_playlist("Mix", [t2], "exportify"), pid)  # re-import replaces
        db.save_playlist("another", [t1], "exportify")
        self.assertEqual([(p["name"], p["size"]) for p in db.playlists()], [("another", 1), ("Mix", 1)])
        self.assertEqual(db.playlist_tracks(pid), [t2])
        db.delete_playlist(pid)
        self.assertEqual([p["name"] for p in db.playlists()], ["another"])
        self.assertEqual(db.playlist_tracks(pid), [])

    def test_deezer_match_cache(self):
        db = Storage(":memory:")
        self.assertIsNone(db.deezer_match("t1"))
        db.set_deezer_match("t1", None)
        self.assertIsNone(db.deezer_match("t1")["deezer_id"])  # looked up, nothing found
        db.set_deezer_match("t2", deezer.DeezerMatch(42, "cover.jpg", "https://www.deezer.com/track/42", "1975"))
        self.assertEqual(db.deezer_match("t2")["deezer_id"], 42)


def dz(id, title, artist, preview=True, readable=True):
    return {"id": id, "title": title, "artist": {"name": artist}, "readable": readable,
            "preview": "https://cdnt-preview.dzcdn.net/x.mp3" if preview else "",
            "album": {"cover_big": f"cover{id}.jpg"}, "link": f"https://www.deezer.com/track/{id}"}


class TestDeezerFind(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {}
        original = deezer._get
        self.addCleanup(setattr, deezer, "_get", original)

        def fake_get(path, **params):
            self.calls.append(path)
            return self.responses.get(path, {"data": []})
        deezer._get = fake_get

    def test_isrc_hit(self):
        self.responses["/track/isrc:GBUM71029604"] = dz(1, "Bohemian Rhapsody", "Queen")
        m = deezer.find(make_track(title="Bohemian Rhapsody - Remastered 2011").__class__(
            **{**make_track().__dict__, "isrc": "GBUM71029604"}))
        self.assertEqual((m.deezer_id, m.cover_url), (1, "cover1.jpg"))
        self.assertEqual(self.calls, ["/track/isrc:GBUM71029604"])

    def test_unplayable_isrc_falls_back_to_scored_search(self):
        self.responses["/track/isrc:X"] = dz(1, "Bohemian Rhapsody", "Queen", preview=False, readable=False)
        self.responses["/search"] = {"data": [dz(2, "Bohemian Rhapsody (Live Aid)", "Queen"),
                                              dz(3, "Bohemian Rhapsody", "Queen"),
                                              dz(4, "Bohemian Rhapsody", "Some Cover Band")]}
        track = make_track(title="Bohemian Rhapsody - Remastered 2011")
        track = track.__class__(**{**track.__dict__, "isrc": "X"})
        self.assertEqual(deezer.find(track).deezer_id, 3)

    def test_no_good_match(self):
        self.responses["/search"] = {"data": [dz(5, "Something Else", "Other Artist")]}
        self.assertIsNone(deezer.find(make_track()))


if __name__ == "__main__":
    unittest.main()
