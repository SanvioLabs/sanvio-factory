"""Run with: python3 -m unittest discover -s tests"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pulse.py"
SKILL = ROOT / "skills" / "pulse" / "SKILL.md"

BANK = """# Team pulse

## alpha
Chip: Alpha chip
Question: How is alpha?
- Good: It went well
- Bad: It went badly

## beta
Chip: Beta chip
Question: How is beta?
- Up: Going up
- Flat: Staying flat
- Down: Going down

## gamma
Chip: Gamma chip
Question: How is gamma?
- Yes: It is
- No: It isn't
"""
MOVED_BANK = """## gamma
Chip: Gamma chip
Question: How is gamma?
- Yes: It is
- No: It isn't

## beta
Chip: Beta chip
Question: How is beta?
- Up: Going up
- Flat: Staying flat
- Down: Going down

## delta
Chip: Delta chip
Question: How is delta?
- Fine: It is fine
- Poor: It is poor
"""
DAY = "2026-03-10"
NO_SKIPS = "Skipped 0 files and 0 lines."


def pick(question_id, label, date=DAY, **extra):
    record = {"date": date, "id": question_id, "answer": label}
    record.update(extra)
    return record


def days_before(day, count):
    return (day - datetime.timedelta(days=count)).isoformat()


class SummaryCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.folder = self.tmp / "shared"
        self.folder.mkdir()
        self.bank()

    def bank(self, text=BANK):
        (self.folder / "questions.md").write_text(text, encoding="utf-8")

    def pulse(self, *args):
        env = dict(os.environ)
        env["SANVIO_PULSE_FOLDER"] = str(self.folder)
        env["LOGNAME"] = "pat"
        env["USER"] = "pat"
        return subprocess.run([sys.executable, str(SCRIPT)] + list(args), env=env, capture_output=True,
                              encoding="utf-8", errors="replace", cwd=str(self.tmp))

    def person(self, name, *records):
        answers = self.folder / "answers"
        answers.mkdir(exist_ok=True)
        lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
        (answers / (name + ".jsonl")).write_text("".join(line + "\n" for line in lines), encoding="utf-8")

    def everyone(self, *records, names=("pat", "sam", "kim")):
        for name in names:
            self.person(name, *records)

    def lines(self, *args):
        result = self.pulse("summary", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout.splitlines()

    def on_day(self):
        return self.lines("--since", DAY, "--until", DAY)

    def assert_refused(self, result, *words):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        for word in words:
            self.assertIn(word, result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class Period(SummaryCase):
    def headings(self, lines):
        return [line for line in lines if line.startswith("## ")]

    def test_both_ends_are_included_and_the_days_outside_are_not(self):
        days = ["2026-03-09", "2026-03-10", "2026-03-12", "2026-03-13"]
        self.everyone(*[pick("beta", "Up", day) for day in days])
        lines = self.lines("--since", "2026-03-10", "--until", "2026-03-12")
        self.assertEqual(lines[0], "# Pulse summary: 2026-03-10 to 2026-03-12")
        self.assertEqual(self.headings(lines), ["## 2026-03-10: Beta chip", "## 2026-03-12: Beta chip"])

    def test_without_since_it_covers_the_14_days_ending_at_until(self):
        until = datetime.date(2026, 3, 20)
        self.everyone(pick("beta", "Up", days_before(until, 14)), pick("beta", "Up", days_before(until, 13)),
                      pick("beta", "Up", until.isoformat()), pick("beta", "Up", days_before(until, -1)))
        lines = self.lines("--until", until.isoformat())
        self.assertEqual(lines[0], "# Pulse summary: 2026-03-07 to 2026-03-20")
        self.assertEqual(self.headings(lines), ["## 2026-03-07: Beta chip", "## 2026-03-20: Beta chip"])

    def test_with_no_flags_it_covers_the_14_days_ending_today(self):
        today = datetime.date.today()
        self.everyone(pick("beta", "Up", days_before(today, 14)), pick("beta", "Up", days_before(today, 13)),
                      pick("beta", "Up", today.isoformat()), pick("beta", "Up", days_before(today, -1)))
        lines = self.lines()
        self.assertEqual(lines[0], "# Pulse summary: {} to {}".format(days_before(today, 13), today.isoformat()))
        self.assertEqual(self.headings(lines), ["## {}: Beta chip".format(days_before(today, 13)),
                                                "## {}: Beta chip".format(today.isoformat())])

    def test_since_alone_runs_to_today(self):
        today = datetime.date.today()
        self.assertEqual(self.lines("--since", days_before(today, 30))[0],
                         "# Pulse summary: {} to {}".format(days_before(today, 30), today.isoformat()))

    def test_until_at_the_start_of_the_calendar_is_not_a_traceback(self):
        self.assertEqual(self.lines("--until", "0001-01-05")[0], "# Pulse summary: 0001-01-01 to 0001-01-05")

    def test_one_day_is_a_period(self):
        self.assertEqual(self.on_day()[0], "# Pulse summary: 2026-03-10 to 2026-03-10")

    def test_until_before_since_says_so_and_exits_1(self):
        result = self.pulse("summary", "--since", "2026-03-11", "--until", "2026-03-10")
        self.assert_refused(result, "--until", "--since", "before")

    def test_a_bad_value_names_its_flag(self):
        for flag in ("--since", "--until"):
            for value in ("yesterday", "2026-13-40"):
                with self.subTest(flag=flag, value=value):
                    result = self.pulse("summary", flag, value)
                    self.assert_refused(result, flag, value)
                    self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_a_date_that_is_not_a_real_yyyy_mm_dd_is_outside_and_not_skipped(self):
        for date in ("not-a-date", "2026-02-30", "20260310", "2026-W11-2", " 2026-03-10"):
            with self.subTest(date=date):
                self.everyone(pick("beta", "Up", date))
                self.assertEqual(self.lines("--since", "2026-01-01", "--until", "2026-12-31")[1:],
                                 ["", "No answers for this period.", "", NO_SKIPS])

    def test_nothing_in_the_period_says_so(self):
        self.everyone(pick("beta", "Up", "2020-01-01"))
        self.assertEqual(self.on_day(), ["# Pulse summary: 2026-03-10 to 2026-03-10", "",
                                         "No answers for this period.", "", NO_SKIPS])

    def test_a_missing_answers_folder_is_no_answers_and_creates_nothing(self):
        self.assertEqual(self.on_day()[1:], ["", "No answers for this period.", "", NO_SKIPS])
        self.assertFalse((self.folder / "answers").exists())


class TheBank(SummaryCase):
    def test_a_bank_that_fails_check_prints_its_problems_and_exits_1(self):
        self.bank("## Bad Id\nChip: Fine\nQuestion: Why?\n- One: First\n- Two: Second\n")
        self.everyone(pick("beta", "Up"))
        result = self.pulse("summary")
        self.assert_refused(result, "Bad Id:", "lowercase")
        self.assertEqual(result.stderr, self.pulse("check").stderr)
        self.assertEqual(result.stderr, self.pulse("results").stderr)


class Layout(SummaryCase):
    def test_the_whole_summary_for_a_bank_question_and_one_that_left_it(self):
        self.person("pat", pick("beta", "Up"), pick("retired", "Zebra"), pick("alpha", "Good", "2026-03-11"))
        self.person("sam", pick("beta", "Up"), pick("retired", "Apple"), pick("alpha", "Good", "2026-03-11"))
        self.person("kim", pick("beta", "Other", other="my words"), pick("retired", "Apple"))
        result = self.pulse("summary", "--since", DAY, "--until", "2026-03-11")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, """# Pulse summary: 2026-03-10 to 2026-03-11

## 2026-03-10: Beta chip
How is beta?

3 answered

- Up: 2
- Flat: 0
- Down: 0
- Other: 1

Other answers:

- my words

## 2026-03-10: retired

3 answered

- Apple: 2
- Zebra: 1

## 2026-03-11: Alpha chip
Fewer than three answered.

Skipped 0 files and 0 lines.
""")

    def test_oldest_first_then_by_id(self):
        self.everyone(pick("gamma", "Yes", "2026-03-11"), pick("beta", "Up", "2026-03-11"), pick("gamma", "Yes"))
        headings = [line for line in self.lines("--since", DAY, "--until", "2026-03-11") if line.startswith("## ")]
        self.assertEqual(headings, ["## 2026-03-10: Gamma chip", "## 2026-03-11: Beta chip",
                                    "## 2026-03-11: Gamma chip"])

    def test_a_label_no_longer_in_the_bank_follows_other_sorted(self):
        self.person("pat", pick("beta", "Sideways"))
        self.person("sam", pick("beta", "Backwards"))
        self.person("kim", pick("beta", "Up"))
        labels = [line for line in self.on_day() if line.startswith("- ")]
        self.assertEqual(labels, ["- Up: 1", "- Flat: 0", "- Down: 0", "- Other: 0", "- Backwards: 1",
                                  "- Sideways: 1"])

    def test_no_other_answers_means_no_other_answers_line(self):
        self.everyone(pick("beta", "Up"))
        self.assertNotIn("Other answers:", self.on_day())


class Grouping(SummaryCase):
    def test_answers_stay_with_the_recorded_id_whatever_the_rotation_says(self):
        rotation = ["alpha", "beta", "gamma"]
        day = datetime.date.fromisoformat(DAY)
        off_rotation = next(q for q in rotation if q != rotation[day.toordinal() % 3])
        self.everyone(pick(off_rotation, "Kept"))
        self.assertIn("- Kept: 3", self.on_day())

    def test_a_question_that_left_the_bank_keeps_its_answers_under_its_id(self):
        self.everyone(pick("alpha", "Good"))
        self.bank(MOVED_BANK)
        self.assertEqual(self.on_day()[1:], ["", "## 2026-03-10: alpha", "", "3 answered", "", "- Good: 3", "",
                                             NO_SKIPS])

    def test_a_question_that_moved_in_the_bank_keeps_its_answers_and_chip(self):
        self.everyone(pick("beta", "Up"), pick("gamma", "Yes"))
        before = self.on_day()
        self.bank(MOVED_BANK)
        self.assertEqual(self.on_day(), before)
        self.assertIn("## 2026-03-10: Beta chip", before)
        self.assertIn("## 2026-03-10: Gamma chip", before)


class Counting(SummaryCase):
    def test_a_person_counts_once_and_their_last_answer_wins(self):
        self.person("pat", pick("beta", "Down"), pick("beta", "Up"))
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Flat"))
        lines = self.on_day()
        self.assertIn("3 answered", lines)
        self.assertIn("- Up: 2", lines)
        self.assertIn("- Flat: 1", lines)
        self.assertIn("- Down: 0", lines)

    def test_a_later_option_drops_an_earlier_other_text(self):
        self.person("pat", pick("beta", "Other", other="words taken back"), pick("beta", "Up"))
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Up"))
        lines = self.on_day()
        self.assertIn("- Other: 0", lines)
        self.assertNotIn("words taken back", "\n".join(lines))
        self.assertNotIn("Other answers:", lines)

    def test_a_later_other_replaces_an_earlier_one(self):
        self.person("pat", pick("beta", "Other", other="first words"), pick("beta", "Other", other="last words"))
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Up"))
        said = "\n".join(self.on_day())
        self.assertIn("- last words", said)
        self.assertNotIn("first words", said)

    def test_the_same_question_on_two_dates_counts_a_person_on_each(self):
        self.everyone(pick("beta", "Up"), pick("beta", "Down", "2026-03-11"))
        lines = self.lines("--since", DAY, "--until", "2026-03-11")
        self.assertEqual(lines.count("3 answered"), 2)

    def test_other_texts_are_sorted_and_only_real_ones_count(self):
        self.person("aaa", pick("beta", "Other", other="zebra words"))
        self.person("bbb", pick("beta", "Other", other="apple words"))
        self.person("ccc", pick("beta", "Other", other="  \n "))
        self.person("ddd", pick("beta", "Other", other=["a list"]))
        self.person("eee", pick("beta", "Other"))
        self.person("fff", pick("beta", "Up", other="stray words"))
        lines = self.on_day()
        at = lines.index("Other answers:")
        self.assertEqual(lines[at:at + 4], ["Other answers:", "", "- apple words", "- zebra words"])
        self.assertEqual(lines[at + 4:], ["", NO_SKIPS])
        self.assertIn("- Other: 5", lines)


class HeldBack(SummaryCase):
    def test_exactly_two_shows_only_the_date_the_chip_and_that_fewer_answered(self):
        self.person("pat", pick("beta", "Up"))
        self.person("sam", pick("beta", "Other", other="my secret words"))
        self.assertEqual(self.on_day()[1:], ["", "## 2026-03-10: Beta chip", "Fewer than three answered.", "",
                                             NO_SKIPS])

    def test_exactly_two_on_a_question_that_left_the_bank_shows_its_id(self):
        self.person("pat", pick("retired", "Other", other="my secret words"))
        self.person("sam", pick("retired", "Kept"))
        self.assertEqual(self.on_day()[1:], ["", "## 2026-03-10: retired", "Fewer than three answered.", "",
                                             NO_SKIPS])

    def test_exactly_three_is_shown(self):
        self.person("pat", pick("beta", "Up"))
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Other", other="my words"))
        lines = self.on_day()
        self.assertIn("3 answered", lines)
        self.assertIn("- my words", lines)
        self.assertNotIn("Fewer than three answered.", lines)

    def test_a_held_back_question_does_not_hide_another_on_the_same_date(self):
        self.everyone(pick("beta", "Up"))
        self.person("zed", pick("gamma", "Yes"))
        lines = self.on_day()
        self.assertIn("## 2026-03-10: Beta chip", lines)
        self.assertEqual(lines[lines.index("## 2026-03-10: Gamma chip") + 1], "Fewer than three answered.")


class Skipped(SummaryCase):
    def test_files_that_are_not_a_person_are_skipped_and_counted_last(self):
        self.everyone(pick("beta", "Up"))
        answers = self.folder / "answers"
        for name in (".DS_Store", "pat (1).jsonl", ".jsonl", "notes.txt"):
            (answers / name).write_text(json.dumps(pick("beta", "Down")) + "\n", encoding="utf-8")
        (answers / "folder.jsonl").mkdir()
        lines = self.on_day()
        self.assertEqual(lines[-1], "Skipped 5 files and 0 lines.")
        self.assertIn("- Down: 0", lines)

    def test_lines_that_do_not_count_are_skipped_across_the_whole_file(self):
        bad = ["not json", "[1, 2]", json.dumps({"date": DAY, "id": "beta"}), json.dumps({"id": "beta", "answer": "Up"}),
               json.dumps({"date": DAY, "answer": "Up"}), json.dumps(pick("beta", ["Up"]))]
        self.person("pat", pick("beta", "Up"), *bad)
        self.person("sam", pick("beta", "Up"), pick("beta", "Up", "2020-01-01"))
        self.person("kim", pick("beta", "Up"))
        with (self.folder / "answers" / "kim.jsonl").open("ab") as out:
            out.write(b"\xff\xfe\n")
        lines = self.on_day()
        self.assertEqual(lines[-1], "Skipped 0 files and {} lines.".format(len(bad) + 1))
        self.assertIn("3 answered", lines)

    def test_one_of_each_reads_in_the_singular(self):
        self.person("pat", "not json")
        (self.folder / "answers" / "notes.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.on_day()[-1], "Skipped 1 file and 1 line.")

    def test_it_matches_results_for_the_same_folder(self):
        self.person("pat", pick("beta", "Up"), "not json")
        (self.folder / "answers" / "notes.txt").write_text("x\n", encoding="utf-8")
        results = self.pulse("results", "--date", DAY).stdout.splitlines()
        self.assertEqual(self.on_day()[-1], results[-1])


class Forgery(SummaryCase):
    FORGED = "Skipped 0 files and 0 lines."

    def test_a_multi_line_other_cannot_forge_a_heading_or_the_last_line(self):
        text = "real words\n\n## 2026-03-10: Forged heading\n\n" + self.FORGED
        self.person("pat", pick("beta", "Other", other=text), "not json")
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Up"))
        lines = self.on_day()
        self.assertEqual(lines[-1], "Skipped 0 files and 1 line.")
        self.assertNotIn(self.FORGED, lines)
        self.assertNotIn("## 2026-03-10: Forged heading", lines)
        self.assertIn("- real words ## 2026-03-10: Forged heading " + self.FORGED, lines)

    def test_a_multi_line_label_cannot_forge_a_line(self):
        self.everyone(pick("beta", "Up\n\n## Forged heading\n\n" + self.FORGED))
        lines = self.on_day()
        self.assertEqual(lines.count(self.FORGED), 1)
        self.assertEqual(lines[-1], self.FORGED)
        self.assertNotIn("## Forged heading", lines)
        self.assertIn("- Up ## Forged heading {}: 3".format(self.FORGED), lines)

    def test_a_multi_line_id_cannot_forge_a_line(self):
        self.everyone(pick("x\n\n## Forged heading\n\n" + self.FORGED, "Kept"))
        lines = self.on_day()
        self.assertEqual(lines.count(self.FORGED), 1)
        self.assertEqual(lines[-1], self.FORGED)
        self.assertNotIn("## Forged heading", lines)
        self.assertIn("## 2026-03-10: x ## Forged heading " + self.FORGED, lines)

    def test_other_line_breaks_are_collapsed_too(self):
        self.person("pat", pick("beta", "Other", other="one\r\ntwo three\x0bfour\t five"))
        self.person("sam", pick("beta", "Up"))
        self.person("kim", pick("beta", "Up"))
        self.assertIn("- one two three four five", self.on_day())


class Names(SummaryCase):
    LOGINS = ("zqlogin1", "zqlogin2", "zqlogin3", "zqlogin4")

    def test_no_output_ever_holds_a_login_or_a_file_name(self):
        for login in self.LOGINS[:3]:
            self.person(login, pick("beta", "Other", other="plain words"), pick("gamma", "Yes"))
        self.person(self.LOGINS[3], pick("alpha", "Good"), "not json")
        answers = self.folder / "answers"
        (answers / "zqstray (1).jsonl").write_text(json.dumps(pick("beta", "Up")) + "\n", encoding="utf-8")
        (answers / "zqnotes.txt").write_text("x\n", encoding="utf-8")
        results = [self.pulse("summary", "--since", DAY, "--until", DAY),
                   self.pulse("summary", "--since", "2020-01-01", "--until", "2020-01-02"),
                   self.pulse("summary", "--since", "2026-03-11", "--until", DAY)]
        self.assertEqual(results[0].returncode, 0, results[0].stderr)
        self.assertIn("- plain words", results[0].stdout)
        for result in results:
            said = result.stdout + result.stderr
            for word in ("zq", ".jsonl", "pat"):
                self.assertNotIn(word, said)

    def test_it_writes_nothing(self):
        self.everyone(pick("beta", "Up"))
        before = sorted(p.as_posix() for p in self.folder.rglob("*"))
        contents = (self.folder / "answers" / "pat.jsonl").read_bytes()
        self.on_day()
        self.assertEqual(sorted(p.as_posix() for p in self.folder.rglob("*")), before)
        self.assertEqual((self.folder / "answers" / "pat.jsonl").read_bytes(), contents)


class Reports(unittest.TestCase):
    def test_a_summary_is_gitignored_and_the_folders_readme_is_not(self):
        def ignored(path):
            return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path], timeout=30).returncode == 0
        self.assertTrue(ignored("reports/pulse/x.md"))
        self.assertFalse(ignored("reports/pulse/README.md"))


class TheSkill(unittest.TestCase):
    def test_it_names_the_second_job_and_its_checks(self):
        text = SKILL.read_text(encoding="utf-8")
        for words in ("Summarise for leadership", "git check-ignore -q", "reports/pulse/"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
