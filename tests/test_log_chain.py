"""Run with: python3 -m unittest discover -s tests"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from log_chain import link, verify  # noqa: E402 (needs scripts/ on the path first)

ENTRIES = [{"ts": "2026-11-0{}T09:00:00Z".format(n), "event": "skill", "name": "skill-{}".format(n)}
           for n in range(1, 6)]


def chained(entries, before=None):
    """Each entry as a raw line, linked to the line before it; before is the line ahead of the first."""
    out = []
    for entry in entries:
        out.append(json.dumps(link(out[-1] if out else before, entry)))
    return out


class Verify(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "me.jsonl"

    def verify(self, lines):
        self.path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return verify(self.path)

    def test_an_intact_log_is_intact(self):
        self.assertEqual(self.verify(chained(ENTRIES)), "intact")

    def test_an_edited_line_breaks_the_line_after_it(self):
        lines = chained(ENTRIES)
        edited = json.loads(lines[2])
        edited["name"] = "something-else"
        lines[2] = json.dumps(edited)
        self.assertEqual(self.verify(lines), 4)

    def test_a_removed_line_breaks_the_line_that_moved_up(self):
        lines = chained(ENTRIES)
        del lines[2]
        self.assertEqual(self.verify(lines), 3)

    def test_an_inserted_line_with_a_valid_prev_breaks_the_line_after_it(self):
        lines = chained(ENTRIES)
        lines.insert(2, json.dumps(link(lines[1], {"ts": "2026-11-02T10:00:00Z", "event": "skill", "name": "x"})))
        self.assertEqual(self.verify(lines), 4)

    def test_an_inserted_line_without_prev_is_the_break(self):
        lines = chained(ENTRIES)
        lines.insert(2, json.dumps({"ts": "2026-11-02T10:00:00Z", "event": "skill", "name": "x"}))
        self.assertEqual(self.verify(lines), 3)

    def test_a_log_with_no_prev_is_unchained(self):
        self.assertEqual(self.verify([json.dumps(e) for e in ENTRIES]), "unchained")

    def test_a_log_with_its_first_lines_dropped_is_intact(self):
        self.assertEqual(self.verify(chained(ENTRIES)[2:]), "intact")

    def test_an_unchained_head_then_a_chained_tail_is_intact(self):
        head = [json.dumps(e) for e in ENTRIES[:2]]
        self.assertEqual(self.verify(head + chained(ENTRIES[2:], before=head[-1])), "intact")

    def test_an_empty_file_is_unchained(self):
        self.path.write_bytes(b"")
        self.assertEqual(verify(self.path), "unchained")

    def test_a_missing_file_is_unchained(self):
        self.assertEqual(verify(self.path.with_name("missing.jsonl")), "unchained")


class Link(unittest.TestCase):
    def test_the_first_line_has_an_empty_prev(self):
        self.assertEqual(link(None, ENTRIES[0])["prev"], "")
        self.assertEqual(link("", ENTRIES[0])["prev"], "")

    def test_prev_is_the_sha256_of_the_raw_line_without_its_newline(self):
        raw = json.dumps(ENTRIES[0])
        expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(link(raw, ENTRIES[1])["prev"], expected)
        self.assertEqual(link(raw + "\n", ENTRIES[1])["prev"], expected)

    def test_the_entry_passed_in_is_not_changed(self):
        entry = dict(ENTRIES[1])
        out = link(json.dumps(ENTRIES[0]), entry)
        self.assertEqual(entry, ENTRIES[1])
        self.assertNotIn("prev", entry)
        self.assertEqual(dict(out, prev=None), dict(ENTRIES[1], prev=None))


if __name__ == "__main__":
    unittest.main()
