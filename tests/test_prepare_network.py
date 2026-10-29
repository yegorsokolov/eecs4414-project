import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.prepare_network import prepare, read_events

HEADER = "SOURCE_SUBREDDIT\tTARGET_SUBREDDIT\tPOST_ID\tTIMESTAMP\tLINK_SENTIMENT\tPROPERTIES\n"


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def raw(self, name, rows, header=HEADER):
        path = self.root/name
        text = header + "".join("\t".join(map(str, r))+"\n" for r in rows)
        if name.endswith(".gz"):
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def rows(self, path):
        with path.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_merge_deduplicate_and_partition_preserves_parallel_events(self):
        a = ("a", "b", "p1", "2014-01-31 23:59:59", -1, "x")
        title = self.raw("title.tsv", [a, a, ("a","a","self","2014-01-01 00:00:00",-1,"x"),
                                      ("a","b","p2","2014-02-01 00:00:00",1,"x")])
        body = self.raw("body.tsv.gz", [(*a[:-1], "different unused properties"),
                                       ("b","a","p3","2014-04-01 00:00:00",-1,"x")])
        out = self.root/"clean"
        result = prepare({"title":title,"body":body},out)
        self.assertEqual(result["summary"]["events"],3)
        self.assertEqual(result["summary"]["negative_events"],2)
        self.assertEqual(result["summary"]["distinct_directed_pairs"],2)
        self.assertEqual(result["summary"]["nodes"],2)
        self.assertEqual(result["overlap_events"],1)
        self.assertEqual(result["inputs"]["title"]["within_source_duplicates"],1)
        self.assertEqual(result["inputs"]["title"]["self_link_rows_removed"],1)
        edges = self.rows(out/"edges.csv")
        self.assertEqual(edges[0]["provenance"],"title|body")
        self.assertEqual(len(self.rows(out/"snapshots/2014-01_negative.csv")),1)
        self.assertEqual(len(self.rows(out/"snapshots/2014-02_nonnegative.csv")),1)
        self.assertEqual(self.rows(out/"snapshots/2014-03_negative.csv"),[])
        self.assertEqual(result["calendar_months"],4)
        monthly=self.rows(out/"monthly_statistics.csv")
        self.assertEqual(sum(int(r["events"]) for r in monthly),3)
        # The month boundary must put midnight February 1 into February, not January.
        self.assertEqual(monthly[1]["negative_events"],"0")

    def test_conflicting_sign_fails_without_publishing_output(self):
        a=("a","b","p","2014-01-01 00:00:00",-1,"x")
        path=self.raw("title.tsv",[a,(*a[:4],1,"x")])
        out=self.root/"clean"
        with self.assertRaisesRegex(ValueError,"Conflicting labels"):
            prepare({"title":path},out)
        self.assertFalse(out.exists())

    def test_strict_validation_reports_row(self):
        for field,value in ((0,""),(2,""),(3,"2014-02-30 00:00:00"),(4,0)):
            row=["a","b","p","2014-01-01 00:00:00",1,"x"]
            row[field]=value
            path=self.raw("bad.tsv",[row])
            with self.assertRaisesRegex(ValueError,"row 2"):
                list(read_events(path))

    def test_post_label_alias_and_empty_dataset(self):
        path=self.raw("empty.tsv",[],HEADER.replace("LINK_SENTIMENT","POST_LABEL"))
        result=prepare({"body":path},self.root/"empty")
        self.assertEqual(result["summary"]["events"],0)
        self.assertEqual(result["summary"]["negative_fraction"],0)
        self.assertFalse(result["complete_title_and_body"])
        self.assertEqual(result["calendar_months"],0)

    def test_repeatable_bytes_and_no_clobber(self):
        path=self.raw("title.tsv",[("b","c","p2","2014-01-02 00:00:00",1,"x"),
                                   ("a","b","p1","2014-01-01 00:00:00",-1,"x")])
        first=prepare({"title":path},self.root/"first")
        second=prepare({"title":path},self.root/"second")
        self.assertEqual(first,second)
        with self.assertRaises(FileExistsError):
            prepare({"title":path},self.root/"first")


if __name__ == "__main__":
    unittest.main()
