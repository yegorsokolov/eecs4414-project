import gzip
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.pattern_counts import (PATTERNS, brute_force_counts, count_patterns,
                                load_negative_events)

HEADER = "SOURCE_SUBREDDIT\tTARGET_SUBREDDIT\tPOST_ID\tTIMESTAMP\tLINK_SENTIMENT\tPROPERTIES\n"


def tsv_row(source, target, timestamp, sentiment=-1):
    """Build one TSV data row with a dummy post id and properties."""
    return f"{source}\t{target}\tpost\t{timestamp}\t{sentiment}\t0.0\n"


class PatternCountTests(unittest.TestCase):
    def load_text(self, text, name="links.tsv"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            if name.endswith(".gz"):
                with gzip.open(path, "wt", encoding="utf-8") as stream:
                    stream.write(text)
            else:
                path.write_text(text, encoding="utf-8")
            return load_negative_events(path)

    def pairs(self, events, delta=1):
        """Return {pattern: pairs} from the fast counter for one delta."""
        table = count_patterns(events, [delta])[delta]
        return {name: table[name]["pairs"] for name in PATTERNS}

    def test_hand_made_example_with_shuffled_rows(self):
        # Shuffled on purpose: the file is not sorted by time. The positive
        # row C->A at 00:30 must be ignored.
        rows = [("D", "B", "04:00:00", -1), ("A", "B", "00:00:00", -1),
                ("B", "E", "05:00:00", -1), ("C", "A", "00:30:00", 1),
                ("A", "C", "03:00:00", -1), ("B", "A", "01:00:00", -1),
                ("A", "B", "02:00:00", -1)]
        text = HEADER + "".join(tsv_row(s, t, f"2020-01-01 {clock}", label)
                                for s, t, clock, label in rows)
        events = self.load_text(text)
        self.assertEqual(len(events), 6)
        expected = {"reciprocal": 2, "repeated": 1, "outward": 3,
                    "converging": 2, "chain": 4}
        self.assertEqual(self.pairs(events), expected)
        self.assertEqual(brute_force_counts(events, [1])[1], count_patterns(events, [1])[1])
        brute = brute_force_counts(events, [1])[1]
        self.assertEqual({name: brute[name]["pairs"] for name in PATTERNS}, expected)

    def test_distinct_followups_can_be_smaller_than_pairs(self):
        # Both A->B events are followed by the same B->A event.
        events = self.load_text(HEADER +
            tsv_row("A", "B", "2020-01-01 00:00:00") +
            tsv_row("A", "B", "2020-01-01 01:00:00") +
            tsv_row("B", "A", "2020-01-01 02:00:00"))
        table = count_patterns(events, [1])[1]
        self.assertEqual(table["reciprocal"], {"pairs": 2, "distinct_followups": 1})
        self.assertEqual(table["repeated"], {"pairs": 1, "distinct_followups": 1})

    def test_window_boundaries(self):
        start = datetime(2020, 1, 1)
        cases = [("23:59:59 counts", timedelta(hours=23, minutes=59, seconds=59), 1),
                 ("exactly 24:00:00 counts", timedelta(days=1), 1),
                 ("24:00:01 does not count", timedelta(days=1, seconds=1), 0),
                 ("equal timestamps do not count", timedelta(0), 0)]
        for label, gap, expected in cases:
            with self.subTest(label):
                events = [("A", "B", start), ("B", "A", start + gap)]
                self.assertEqual(self.pairs(events)["reciprocal"], expected)
                self.assertEqual(
                    brute_force_counts(events, [1])[1]["reciprocal"]["pairs"], expected)

    def test_fast_matches_brute_force_on_random_data(self):
        names = ["a", "b", "c", "d", "e", "f"]
        for label, step in (("six-hour grid", 6 * 3600), ("seconds", 1)):
            rng = random.Random(4414)
            events = []
            for _ in range(200):
                source, target = rng.sample(names, 2)
                events.append((source, target,
                               datetime(2020, 1, 1) + timedelta(seconds=step * rng.randrange(10 * 86400 // step))))
            with self.subTest(label):
                self.assertEqual(count_patterns(events, [1, 3, 7]),
                                 brute_force_counts(events, [1, 3, 7]))

    def test_gzip_input_matches_plain_input(self):
        text = HEADER + tsv_row("a", "b", "2020-01-01 00:00:00")
        self.assertEqual(self.load_text(text, "links.tsv.gz"), self.load_text(text))

    def test_negative_self_link_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "self-link"):
            self.load_text(HEADER + tsv_row("a", "a", "2020-01-01 00:00:00"))

    def test_positive_self_link_is_ignored(self):
        events = self.load_text(HEADER + tsv_row("a", "a", "2020-01-01 00:00:00", 1))
        self.assertEqual(events, [])

    def test_empty_input(self):
        self.assertEqual(self.pairs([]), {name: 0 for name in PATTERNS})

    def test_invalid_rows_have_line_numbers(self):
        with self.assertRaisesRegex(ValueError, "row 2"):
            self.load_text(HEADER + tsv_row("a", "b", "bad-date"))


if __name__ == "__main__":
    unittest.main()
