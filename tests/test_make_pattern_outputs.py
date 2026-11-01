import importlib.util
import tempfile
import unittest
from pathlib import Path

from src.make_pattern_outputs import PATTERNS, format_count, make_outputs, read_counts

ROOT = Path(__file__).resolve().parents[1]
HEADER = "delta_days,pattern,pairs,distinct_followups\n"


def tiny_csv_text():
    """Build a CSV where pairs = 1000 * rank and distinct = rank, with one big value."""
    rows = []
    for delta_index, delta in enumerate((1, 3, 7)):
        for pattern_index, pattern in enumerate(PATTERNS):
            rank = delta_index * 10 + pattern_index + 1
            rows.append(f"{delta},{pattern},{rank * 1000},{rank}\n")
    rows[2] = "1,outward,1234567,26578\n"
    return HEADER + "".join(rows)


class OutputTests(unittest.TestCase):
    def build(self, text, metric="distinct_followups"):
        """Write text to a temp CSV, run make_outputs, and return (tex dict, paths)."""
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        csv_path = Path(directory.name) / "counts.csv"
        csv_path.write_text(text, encoding="utf-8")
        outdir = Path(directory.name) / "out"
        written = make_outputs(csv_path, outdir, metric)
        return outdir, written

    def table_lines(self, path):
        return path.read_text(encoding="utf-8").splitlines()

    def test_format_count(self):
        self.assertEqual(format_count(7), "7")
        self.assertEqual(format_count(999), "999")
        self.assertEqual(format_count(26578), "26{,}578")
        self.assertEqual(format_count(1234567), "1{,}234{,}567")

    def test_distinct_table_layout_and_numbers(self):
        outdir, _ = self.build(tiny_csv_text())
        lines = self.table_lines(outdir / "pattern_table_distinct.tex")
        self.assertEqual(lines[:4], ["\\begin{tabular}{lrrr}", "\\toprule",
                                     "Pattern & 1 day & 3 days & 7 days \\\\", "\\midrule"])
        self.assertEqual(lines[-2:], ["\\bottomrule", "\\end{tabular}"])
        self.assertEqual(lines[4:9], [
            "Reciprocal & 1 & 11 & 21 \\\\",
            "Repeated & 2 & 12 & 22 \\\\",
            "Outward & 26{,}578 & 13 & 23 \\\\",
            "Converging & 4 & 14 & 24 \\\\",
            "Chain & 5 & 15 & 25 \\\\"])
        self.assertEqual(len(lines), 11)

    def test_pairs_table_uses_pairs_and_separators(self):
        outdir, _ = self.build(tiny_csv_text())
        lines = self.table_lines(outdir / "pattern_table_pairs.tex")
        self.assertEqual(lines[4], "Reciprocal & 1{,}000 & 11{,}000 & 21{,}000 \\\\")
        self.assertEqual(lines[6], "Outward & 1{,}234{,}567 & 13{,}000 & 23{,}000 \\\\")

    def test_tables_are_bare_tabulars(self):
        outdir, _ = self.build(tiny_csv_text())
        for name in ("distinct", "pairs"):
            text = (outdir / f"pattern_table_{name}.tex").read_text(encoding="utf-8")
            for forbidden in ("\\begin{table", "\\caption", "\\label"):
                self.assertNotIn(forbidden, text)

    @unittest.skipIf(importlib.util.find_spec("matplotlib") is None, "matplotlib missing")
    def test_figure_is_created_for_both_metrics(self):
        for metric in ("distinct_followups", "pairs"):
            with self.subTest(metric=metric):
                outdir, written = self.build(tiny_csv_text(), metric)
                figure = outdir / "pattern_counts.pdf"
                self.assertIn(figure, written)
                self.assertEqual(figure.read_bytes()[:4], b"%PDF")

    def test_tables_are_written_when_matplotlib_is_missing(self):
        def failing_figure(*args):
            raise ImportError("no matplotlib")
        import src.make_pattern_outputs as module
        original = module.write_figure
        module.write_figure = failing_figure
        self.addCleanup(setattr, module, "write_figure", original)
        outdir, written = self.build(tiny_csv_text())
        self.assertTrue((outdir / "pattern_table_distinct.tex").exists())
        self.assertTrue((outdir / "pattern_table_pairs.tex").exists())
        self.assertEqual(len(written), 2)

    def test_bad_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            for text, message in (("a,b\n", "Missing columns"),
                                  (HEADER + "1,reciprocal,x,2\n", "row 2"),
                                  (HEADER + "1,reciprocal,2,2\n", "no row for delta")):
                with self.subTest(message=message):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        read_counts(path)


if __name__ == "__main__":
    unittest.main()
