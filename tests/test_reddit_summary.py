import tempfile
import unittest
from pathlib import Path

from src.reddit_summary import summarize

HEADER = "SOURCE_SUBREDDIT\tTARGET_SUBREDDIT\tTIMESTAMP\tLINK_SENTIMENT\n"


class SummaryTests(unittest.TestCase):
    def summarize_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "links.tsv"
            path.write_text(text, encoding="utf-8")
            return summarize(path)

    def test_example_distinguishes_events_from_edges(self):
        result = summarize(Path(__file__).resolve().parents[1] / "data/example.tsv")
        self.assertEqual(result["total_events"], 4)
        self.assertEqual(result["negative_events"], 3)
        self.assertEqual(result["negative_event_fraction"], 0.75)
        self.assertEqual(result["negative_nodes"], 3)
        self.assertEqual(result["unique_directed_negative_edges"], 2)

    def test_direction_self_links_and_unsorted_time(self):
        result = self.summarize_text(HEADER +
            "a\tb\t2020-01-02 00:00:00\t-1\n"
            "b\ta\t2020-01-01 00:00:00\t-1\n"
            "a\ta\t2020-01-03 00:00:00\t-1\n")
        self.assertEqual(result["unique_directed_negative_edges"], 3)
        self.assertEqual(result["negative_self_edges"], 1)
        self.assertEqual(result["first_negative_timestamp"], "2020-01-01 00:00:00")
        self.assertEqual(result["last_negative_timestamp"], "2020-01-03 00:00:00")

    def test_empty_and_positive_only(self):
        for rows in ("", "a\tb\t2020-01-01 00:00:00\t1\n"):
            with self.subTest(rows=rows):
                result = self.summarize_text(HEADER + rows)
                self.assertEqual(result["negative_nodes"], 0)
                self.assertEqual(result["negative_event_fraction"], 0.0)
                self.assertIsNone(result["first_negative_timestamp"])

    def test_documented_label_alias(self):
        result = self.summarize_text(HEADER.replace("LINK_SENTIMENT", "POST_LABEL") +
            "a\tb\t2020-01-01 00:00:00\t-1\n")
        self.assertEqual(result["negative_events"], 1)

    def test_missing_label(self):
        with self.assertRaisesRegex(ValueError, "Missing label"):
            self.summarize_text("SOURCE_SUBREDDIT\tTARGET_SUBREDDIT\tTIMESTAMP\n")

    def test_missing_columns(self):
        with self.assertRaisesRegex(ValueError, "Missing columns"):
            self.summarize_text("source\ttarget\n")

    def test_invalid_rows_have_line_numbers(self):
        for row in ("a\tb\tbad-date\t-1", "a\tb\t2020-01-01 00:00:00\t0", "\tb\t2020-01-01 00:00:00\t-1", "a\tb"):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "row 2"):
                self.summarize_text(HEADER + row + "\n")


if __name__ == "__main__":
    unittest.main()
