import random
import unittest

from _helpers import make_track
from music_guessr import stats
from music_guessr.game import GameSession, evaluate
from music_guessr.storage import Storage


class TestGame(unittest.TestCase):
    def test_scoring(self):
        t = make_track()
        r = evaluate(t, "queen", "Bohemian Rhapsody", "1975")
        self.assertTrue(r.perfect)
        self.assertEqual(r.points, 4)
        r = evaluate(t, "", "bohemian rapsody", "1977")
        self.assertEqual((r.artist_ok, r.title_ok, r.year_diff, r.points), (False, True, 2, 2))
        r = evaluate(t, "abba", "x", "abc")
        self.assertEqual((r.points, r.year_diff), (0, None))

    def test_any_featured_artist_counts(self):
        t = make_track(artists=(("a1", "Calvin Harris"), ("a2", "Rihanna")))
        r = evaluate(t, "rihanna", "", None)
        self.assertEqual([a.name for a in r.matched_artists], ["Rihanna"])

    def test_session(self):
        tracks = [make_track(id=f"t{i}") for i in range(3)]
        g = GameSession(tracks, skip_ids={"t0"}, rng=random.Random(1))
        self.assertEqual(g.remaining, 2)
        self.assertNotEqual(g.next_track().id, "t0")
        g.submit("queen", "", "")
        self.assertEqual(g.score, 1)
        start = g.snippet_start_ms(tracks[0])
        self.assertTrue(0.2 * 354_000 <= start <= 0.6 * 354_000)


class TestStorageAndStats(unittest.TestCase):
    def test_flow(self):
        db = Storage(":memory:")
        t1 = make_track()
        t2 = make_track(id="t2", title="Waterloo", artists=(("a2", "ABBA"),), year=1974)
        db.record_round(t1, evaluate(t1, "Queen", "Bohemian Rhapsody", 1975), played_at="2026-11-01T10:00:00")
        db.record_round(t2, evaluate(t2, "ABBA", "nope", 1980), played_at="2026-11-02T10:00:00")
        db.record_round(t1, evaluate(t1, "Queen", "bohemian rhapsody", 1974), played_at="2026-11-02T11:00:00")

        self.assertEqual([s["title"] for s in db.guessed_songs()], ["Bohemian Rhapsody - Remastered 2011"])
        self.assertEqual(db.guessed_songs()[0]["times_guessed"], 2)
        self.assertEqual([a["name"] for a in db.guessed_artists()], ["ABBA", "Queen"])

        db.set_artist_wiki("a1", "https://en.wikipedia.org/wiki/Queen_(band)")
        self.assertEqual([a["name"] for a in db.artists_missing_wiki()], ["ABBA"])

        s = stats.compute(db.rounds())
        self.assertEqual(s.rounds, 3)
        self.assertEqual(s.points, 4 + 1 + 3)
        self.assertEqual(s.best_streak, 1)
        self.assertEqual(s.current_streak, 1)
        self.assertEqual(s.perfect_rounds, 1)
        self.assertEqual(s.top_artists[0], ("Queen", 2))
        self.assertEqual(s.points_per_day, [("2026-11-01", 4), ("2026-11-02", 4)])
        self.assertEqual([d for d, _, _ in s.decade_accuracy], ["1970s"])

    def test_empty(self):
        self.assertEqual(stats.compute([]).rounds, 0)


if __name__ == "__main__":
    unittest.main()
