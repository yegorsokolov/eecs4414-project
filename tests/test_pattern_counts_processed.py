"""pattern_counts.py must give identical results on Role A's edges.csv and on raw TSV."""
import tempfile
import unittest
from pathlib import Path

from src.pattern_counts import count_patterns, load_negative_events

ROWS = [  # (source, target, timestamp, sentiment)
    ("A", "B", "2014-01-01 00:00:00", -1), ("B", "A", "2014-01-01 01:00:00", -1),
    ("C", "A", "2014-01-01 00:30:00", 1), ("A", "C", "2014-01-01 03:00:00", -1),
    ("D", "B", "2014-01-01 04:00:00", -1), ("B", "E", "2014-01-01 05:00:00", -1),
]


def write(directory, name, text):
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return path


class ProcessedInputTests(unittest.TestCase):
    def test_edges_csv_matches_raw_tsv(self):
        tsv = "SOURCE_SUBREDDIT\tTARGET_SUBREDDIT\tPOST_ID\tTIMESTAMP\tLINK_SENTIMENT\tPROPERTIES\n"
        tsv += "".join(f"{s}\t{t}\tp{i}\t{ts}\t{l}\t0.0\n" for i, (s, t, ts, l) in enumerate(ROWS))
        csv = "event_id,source,target,post_id,timestamp,sentiment,provenance\n"
        csv += "".join(f"{i},{s},{t},p{i},{ts},{l},title\n" for i, (s, t, ts, l) in enumerate(ROWS))
        with tempfile.TemporaryDirectory() as directory:
            raw = load_negative_events(write(directory, "links.tsv", tsv))
            processed = load_negative_events(write(directory, "edges.csv", csv))
        self.assertEqual(sorted(raw), sorted(processed))
        self.assertEqual(len(processed), 5)  # the positive C->A row is skipped
        self.assertEqual(count_patterns(raw, [1, 7]), count_patterns(processed, [1, 7]))

    def test_csv_without_expected_columns_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write(directory, "other.csv", "a,b,c\n1,2,3\n")
            with self.assertRaises(ValueError):
                load_negative_events(path)


if __name__ == "__main__":
    unittest.main()
