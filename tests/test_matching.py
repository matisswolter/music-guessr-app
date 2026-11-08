import unittest

import _helpers  # noqa: F401
from music_guessr.matching import clean_title, is_match, title_matches


class TestMatching(unittest.TestCase):
    def test_clean_title(self):
        self.assertEqual(clean_title("Bohemian Rhapsody - Remastered 2011"), "Bohemian Rhapsody")
        self.assertEqual(clean_title("Stay (feat. Justin Bieber)"), "Stay")
        self.assertEqual(clean_title("Help! [Live]"), "Help!")
        self.assertEqual(clean_title("(I Can't Get No) Satisfaction"), "(I Can't Get No) Satisfaction")
        self.assertEqual(clean_title("Hey Jude - Love Me Do"), "Hey Jude - Love Me Do")

    def test_fuzzy(self):
        self.assertTrue(is_match("beatles", "The Beatles"))
        self.assertTrue(is_match("Beyonce", "Beyoncé"))
        self.assertTrue(is_match("simon and garfunkel", "Simon & Garfunkel"))
        self.assertTrue(is_match("Fleetwod Mac", "Fleetwood Mac"))
        self.assertFalse(is_match("Queen", "Muse"))
        self.assertFalse(is_match("", "Muse"))
        self.assertFalse(is_match("U3", "U2"))

    def test_title(self):
        self.assertTrue(title_matches("bohemian rhapsody", "Bohemian Rhapsody - Remastered 2011"))
        self.assertFalse(title_matches("yesterday", "Bohemian Rhapsody"))


if __name__ == "__main__":
    unittest.main()
