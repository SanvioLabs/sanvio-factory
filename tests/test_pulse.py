"""Run with: python3 -m unittest discover -s tests"""
import ast
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pulse.py"
SKILL = ROOT / "skills" / "pulse" / "SKILL.md"
GUIDE = ROOT / "skills" / "pulse" / "README.md"
EXAMPLE = ROOT / "skills" / "pulse" / "questions.example.md"
STANDUP = ROOT / "skills" / "standup" / "SKILL.md"
CLEARED = ("A source is cleared only when its `Cleared for this tool` cell in `company/DATA.md` is exactly "
           "`yes`, ignoring case and surrounding spaces. Anything else isn't cleared: `no`, `unconfirmed`, "
           "blank, `yes` followed by anything (such as `yes, summaries only`), or no row.")
STDLIB = {"argparse", "collections", "datetime", "getpass", "json", "os", "re", "sys"}

BANK = """# Team pulse

Some prose, and a line that isn't an option yet:
- Stray: before the first heading
Chip: Stray
### not-a-heading

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
IDS = ["alpha", "beta", "gamma"]
TWO_OPTIONS = "- One: First\n- Two: Second\n"


def question(body=TWO_OPTIONS, chip="Chip: Fine\n", ask="Question: Why?\n", heading="## one\n"):
    return heading + chip + ask + body


def flat(text):
    return " ".join(text.split())


class PulseCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.folder = self.tmp / "shared"
        self.folder.mkdir()
        self.today = datetime.date.today()
        self.yesterday = (self.today - datetime.timedelta(days=1)).isoformat()

    def pulse(self, *args, folder=None, unset=False, login="pat", old_name=False):
        env = dict(os.environ)
        env.pop("SANVIO_PULSE_FOLDER", None)
        env.pop("HARNESS_PULSE_FOLDER", None)
        if not unset:
            env[old_name and "HARNESS_PULSE_FOLDER" or "SANVIO_PULSE_FOLDER"] = str(folder or self.folder)
        env["LOGNAME"] = login
        env["USER"] = login
        return subprocess.run([sys.executable, str(SCRIPT)] + list(args), env=env, capture_output=True,
                              encoding="utf-8", errors="replace", cwd=str(self.tmp))

    def bank(self, text=BANK):
        (self.folder / "questions.md").write_text(text, encoding="utf-8")

    def files(self):
        return sorted(p.relative_to(self.folder).as_posix() for p in self.folder.rglob("*"))

    def said(self, result):
        return flat(result.stdout + " " + result.stderr)

    def today_id(self):
        return IDS[self.today.toordinal() % len(IDS)]

    def not_today_id(self):
        return IDS[(self.today.toordinal() + 1) % len(IDS)]

    def assert_refused(self, result, before, *words):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.files(), before)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip(), "a refusal says why")
        for word in words:
            self.assertIn(word, self.said(result))

    def answers(self, name="pat"):
        path = self.folder / "answers" / (name + ".jsonl")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def person(self, name, *records):
        answers = self.folder / "answers"
        answers.mkdir(exist_ok=True)
        lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
        (answers / (name + ".jsonl")).write_text("".join(line + "\n" for line in lines), encoding="utf-8")

    def pick(self, question_id, label, date=None, **extra):
        record = {"date": date or self.yesterday, "id": question_id, "answer": label}
        record.update(extra)
        return record


class Folder(PulseCase):
    COMMANDS = (["check"], ["question"], ["answer", "alpha", "1"], ["results"])

    def test_unset_says_so_says_how_and_writes_nothing(self):
        self.bank()
        before = self.files()
        for command in self.COMMANDS:
            with self.subTest(command=command):
                result = self.pulse(*command, unset=True)
                self.assert_refused(result, before, "SANVIO_PULSE_FOLDER", "isn't set", "export")
                self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_a_folder_that_does_not_exist_says_so_and_is_not_created(self):
        missing = self.tmp / "nowhere"
        for command in self.COMMANDS:
            with self.subTest(command=command):
                result = self.pulse(*command, folder=missing)
                self.assertEqual(result.returncode, 1)
                self.assertIn("doesn't exist", self.said(result))
                self.assertIn("export", self.said(result))
                self.assertEqual(len(result.stderr.strip().splitlines()), 1)
                self.assertFalse(missing.exists())

    def test_the_old_variable_no_longer_names_the_folder(self):
        self.bank()
        result = self.pulse("question", "--json", old_name=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SANVIO_PULSE_FOLDER isn't set", self.said(result))

    def test_the_folder_is_checked_before_the_command(self):
        result = self.pulse("question", "--date", "not-a-date", unset=True)
        self.assertIn("SANVIO_PULSE_FOLDER", self.said(result))
        self.assertNotIn("--date", self.said(result))


class BankProblems(PulseCase):
    CASES = {
        "id with capitals": (question(heading="## One\n"), "One:", "lowercase"),
        "id with a space": (question(heading="## one two\n"), "one two:", "lowercase"),
        "no chip": (question(chip=""), "one:", "chip"),
        "empty chip": (question(chip="Chip:   \n"), "one:", "chip"),
        "chip of 13": (question(chip="Chip: Thirteen char\n"), "one:", "12"),
        "no question": (question(ask=""), "one:", "question is missing"),
        "empty question": (question(ask="Question:\n"), "one:", "question is missing"),
        "empty label": (question("- : First\n- Two: Second\n"), "one:", "no label"),
        "empty description": (question("- One:\n- Two: Second\n"), "one:", "no description"),
        "no colon": (question("- One\n- Two: Second\n"), "one:", "no description"),
        "one option": (question("- One: First\n"), "one:", "fewer than 2"),
        "no options": (question(""), "one:", "fewer than 2"),
        "five options": (question("".join("- L{}: d\n".format(n) for n in range(5))), "one:", "more than 4"),
        "same label twice": (question("- One: First\n- One: Second\n"), "one:", "two options"),
        "option named Other": (question("- One: First\n- Other: Second\n"), "one:", "Other"),
        "same id twice": (question() + question(), "one:", "two questions"),
        "no questions": ("# Only a title\n\nSome prose.\n", "questions.md:", "no questions"),
    }

    def test_check_names_each_problem_and_exits_1_writing_nothing(self):
        for name, (text, where, words) in self.CASES.items():
            with self.subTest(name):
                self.bank(text)
                before = self.files()
                self.assert_refused(self.pulse("check"), before, where, words)

    def test_every_other_command_prints_the_same_problems_and_refuses(self):
        for name, (text, where, words) in self.CASES.items():
            self.bank(text)
            before = self.files()
            expected = self.pulse("check").stderr
            for command in (["question"], ["question", "--json"], ["answer", "one", "1"], ["results"]):
                with self.subTest(name, command=command):
                    result = self.pulse(*command)
                    self.assert_refused(result, before)
                    self.assertEqual(result.stderr, expected)

    def test_a_missing_bank_is_a_problem_for_every_command(self):
        for command in (["check"], ["question"], ["answer", "one", "1"], ["results"]):
            with self.subTest(command=command):
                self.assert_refused(self.pulse(*command), [], "questions.md:", "no questions.md")

    def test_undecodable_bytes_are_a_problem_not_a_traceback(self):
        (self.folder / "questions.md").write_bytes(b"## one\nChip: \xff\xfe\n")
        result = self.pulse("check")
        self.assert_refused(result, ["questions.md"], "questions.md:", "UTF-8")
        self.assertNotIn("Traceback", result.stderr)

    def test_every_problem_is_listed_not_just_the_first(self):
        self.bank(question(chip="", ask="") + question(heading="## TWO\n"))
        said = self.said(self.pulse("check"))
        for words in ("one: the chip", "one: the question", "TWO: the id"):
            self.assertIn(words, said)

    def test_a_good_bank_prints_its_count_and_exits_0(self):
        self.bank()
        result = self.pulse("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3 questions", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_a_chip_of_exactly_12_passes(self):
        self.bank(question(chip="Chip: Twelve chars\n"))
        self.assertEqual(self.pulse("check").returncode, 0)

    def test_a_byte_order_mark_is_not_part_of_the_first_line(self):
        (self.folder / "questions.md").write_bytes(b"\xef\xbb\xbf" + question().encode("utf-8"))
        result = self.pulse("question", "--json", "--date", "2026-01-01")
        self.assertEqual(json.loads(result.stdout)["id"], "one")

    def test_what_is_not_part_of_a_question_is_ignored(self):
        self.bank()
        result = self.pulse("check")
        self.assertIn("3 questions", result.stdout)
        day = datetime.date(2026, 3, 2)
        day += datetime.timedelta(days=(0 - day.toordinal()) % 3)
        options = json.loads(self.pulse("question", "--json", "--date", day.isoformat()).stdout)
        self.assertEqual(options["id"], "alpha")
        self.assertEqual([o["label"] for o in options["question"]["options"]], ["Good", "Bad"])


class Question(PulseCase):
    def setUp(self):
        super().setUp()
        self.bank()

    def test_the_index_is_the_ordinal_modulo_the_count_in_file_order(self):
        start = datetime.date(2026, 5, 1)
        for offset in range(7):
            day = start + datetime.timedelta(days=offset)
            result = self.pulse("question", "--json", "--date", day.isoformat())
            self.assertEqual(json.loads(result.stdout)["id"], IDS[day.toordinal() % 3], day)

    def test_with_no_date_it_is_todays_local_date(self):
        data = json.loads(self.pulse("question", "--json").stdout)
        self.assertEqual(data["date"], self.today.isoformat())
        self.assertEqual(data["id"], self.today_id())

    def test_the_plain_text_has_date_chip_question_and_numbered_options(self):
        day = datetime.date(2026, 5, 1)
        day += datetime.timedelta(days=(1 - day.toordinal()) % 3)  # beta, the one with three options
        result = self.pulse("question", "--date", day.isoformat())
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertIn(day.isoformat(), lines[0])
        self.assertIn("beta", lines[0])
        self.assertEqual(lines[1:], ["Beta chip", "How is beta?", "1. Up: Going up", "2. Flat: Staying flat",
                                     "3. Down: Going down"])

    def test_json_is_exactly_the_shape_the_window_takes(self):
        day = datetime.date(2026, 5, 1)
        day += datetime.timedelta(days=(0 - day.toordinal()) % 3)
        result = self.pulse("question", "--json", "--date", day.isoformat())
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout), {
            "date": day.isoformat(), "id": "alpha", "answered": None,
            "question": {"question": "How is alpha?", "header": "Alpha chip", "multiSelect": False,
                         "options": [{"label": "Good", "description": "It went well"},
                                     {"label": "Bad", "description": "It went badly"}]}})

    def test_answered_is_this_persons_last_answer_for_that_date_and_id(self):
        day = self.today.isoformat()
        self.person("pat", self.pick(self.today_id(), "First", day), self.pick(self.today_id(), "Last", day))
        self.person("sam", self.pick(self.today_id(), "Theirs", day))
        data = json.loads(self.pulse("question", "--json").stdout)
        self.assertEqual(data["answered"], "Last")

    def test_answered_ignores_another_date_or_id(self):
        self.person("pat", self.pick(self.today_id(), "Yesterday"),
                    self.pick(self.not_today_id(), "Elsewhere", self.today.isoformat()))
        self.assertIsNone(json.loads(self.pulse("question", "--json").stdout)["answered"])

    def test_answered_skips_a_line_that_does_not_count(self):
        day = self.today.isoformat()
        self.person("pat", self.pick(self.today_id(), "Kept", day), "not json",
                    json.dumps(self.pick(self.today_id(), ["a"], day)))
        self.assertEqual(json.loads(self.pulse("question", "--json").stdout)["answered"], "Kept")

    def test_it_writes_nothing(self):
        before = self.files()
        self.pulse("question")
        self.pulse("question", "--json")
        self.assertEqual(self.files(), before)

    def test_a_bad_date_is_a_one_line_refusal(self):
        before = self.files()
        for command in (["question"], ["answer", "alpha", "1"], ["results"]):
            for value in ("yesterday", "2026-13-40"):
                with self.subTest(command=command, value=value):
                    result = self.pulse(*(command + ["--date", value]))
                    self.assert_refused(result, before, "--date")
                    self.assertEqual(len(result.stderr.strip().splitlines()), 1)


class Answer(PulseCase):
    def setUp(self):
        super().setUp()
        self.bank()

    def other_file(self, content, name="words.txt"):
        path = self.tmp / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)

    def test_a_number_appends_the_label_and_makes_the_answers_folder(self):
        result = self.pulse("answer", self.today_id(), "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        options = {"alpha": "Good", "beta": "Up", "gamma": "Yes"}
        self.assertEqual(self.answers(), [{"date": self.today.isoformat(), "id": self.today_id(),
                                           "answer": options[self.today_id()]}])

    def test_it_writes_no_other_file(self):
        self.pulse("answer", self.today_id(), "1")
        self.assertEqual(self.files(), ["answers", "answers/pat.jsonl", "questions.md"])

    def test_the_number_is_the_options_place_from_one(self):
        day = datetime.date(2026, 5, 1)
        day += datetime.timedelta(days=(2 - day.toordinal()) % 3)
        self.pulse("answer", "gamma", "2", "--date", day.isoformat())
        self.assertEqual(self.answers()[0]["answer"], "No")

    def test_a_second_answer_is_appended(self):
        self.pulse("answer", self.today_id(), "1")
        self.pulse("answer", self.today_id(), "2")
        self.assertEqual(len(self.answers()), 2)
        self.assertEqual(json.loads(self.pulse("question", "--json").stdout)["answered"], self.answers()[1]["answer"])

    def test_other_file_records_the_persons_words_stripped(self):
        path = self.other_file("  In my own words \n\n")
        result = self.pulse("answer", self.today_id(), "--other-file", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.answers(), [{"date": self.today.isoformat(), "id": self.today_id(),
                                           "answer": "Other", "other": "In my own words"}])
        self.assertNotIn("In my own words", result.stdout)

    def test_date_answers_another_day_and_any_question_in_the_bank(self):
        result = self.pulse("answer", self.not_today_id(), "1", "--date", self.yesterday)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.answers()[0]["date"], self.yesterday)
        self.assertEqual(self.answers()[0]["id"], self.not_today_id())

    def test_today_itself_passes_as_a_date(self):
        result = self.pulse("answer", self.today_id(), "1", "--date", self.today.isoformat())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_file_is_named_after_the_login_made_safe(self):
        result = self.pulse("answer", self.today_id(), "1", login="a/b c")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.files(), ["answers", "answers/a_b_c.jsonl", "questions.md"])

    def test_the_refusals_write_nothing_not_even_the_answers_folder(self):
        before = self.files()
        tomorrow = (self.today + datetime.timedelta(days=1)).isoformat()
        words = self.other_file("words")
        cases = {
            "id not in the bank": (["answer", "nope", "1"], "isn't in the bank"),
            "id not in the bank with a date": (["answer", "nope", "1", "--date", self.yesterday], "isn't in the bank"),
            "not today's question": (["answer", self.not_today_id(), "1"], "isn't today's question"),
            "number zero": (["answer", self.today_id(), "0"], "options"),
            "number past the end": (["answer", self.today_id(), "5"], "options"),
            "not a number": (["answer", self.today_id(), "abc"], "options"),
            "negative": (["answer", self.today_id(), "-1"], ""),
            "padded": (["answer", self.today_id(), "01"], "options"),
            "non-ascii digit": (["answer", self.today_id(), "١"], "options"),
            "after today": (["answer", self.today_id(), "1", "--date", tomorrow], "after today"),
            "both": (["answer", self.today_id(), "1", "--other-file", words], "one of"),
            "neither": (["answer", self.today_id()], "one of"),
            "empty other": (["answer", self.today_id(), "--other-file", self.other_file("", "e.txt")], "empty"),
            "blank other": (["answer", self.today_id(), "--other-file", self.other_file(" \n\n", "b.txt")], "empty"),
            "missing other": (["answer", self.today_id(), "--other-file", str(self.tmp / "gone.txt")], "can't be read"),
            "undecodable other": (["answer", self.today_id(), "--other-file", self.other_file(b"\xff\xfe", "u.txt")],
                                  "UTF-8"),
        }
        for name, (command, words_said) in cases.items():
            with self.subTest(name):
                result = self.pulse(*command)
                self.assert_refused(result, before, words_said)
                self.assertNotIn("Traceback", result.stderr)

    def test_bad_usage_exits_1_not_2(self):
        before = self.files()
        for command in ([], ["nonsense"], ["answer"], ["question", "--nonsense"]):
            with self.subTest(command=command):
                self.assert_refused(self.pulse(*command), before)


class Results(PulseCase):
    def setUp(self):
        super().setUp()
        self.bank()

    def lines(self, *args):
        result = self.pulse("results", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def three_on_beta(self):
        self.person("pat", self.pick("beta", "Up"))
        self.person("sam", self.pick("beta", "Up"))
        self.person("kim", self.pick("beta", "Other", other="my secret words"))

    def test_it_counts_each_option_with_zeros_and_other_in_bank_order(self):
        self.three_on_beta()
        self.assertEqual(self.lines(), ["Results for {}".format(self.yesterday), "Beta chip: 3 answered",
                                        "  Up: 2", "  Flat: 0", "  Down: 0", "  Other: 1",
                                        "Skipped 0 files and 0 lines."])

    def test_it_defaults_to_yesterday_and_date_gives_another_day(self):
        self.three_on_beta()
        self.assertIn("No answers for this date.", self.lines("--date", "2020-01-01"))
        self.assertEqual(self.lines("--date", "2020-01-01")[0], "Results for 2020-01-01")
        self.assertIn("Beta chip: 3 answered", self.lines("--date", self.yesterday))

    def test_no_output_ever_holds_a_login_or_other_text(self):
        self.three_on_beta()
        self.person("zed", self.pick("gamma", "Other", other="more secret words"))
        result = self.pulse("results")
        for word in ("pat", "sam", "kim", "zed", "secret"):
            self.assertNotIn(word, result.stdout + result.stderr)

    def test_a_person_counts_once_and_their_last_answer_wins(self):
        self.person("pat", self.pick("beta", "Down"), self.pick("beta", "Up"))
        self.person("sam", self.pick("beta", "Up"))
        self.person("kim", self.pick("beta", "Flat"))
        lines = self.lines()
        self.assertIn("Beta chip: 3 answered", lines)
        self.assertIn("  Up: 2", lines)
        self.assertIn("  Flat: 1", lines)
        self.assertIn("  Down: 0", lines)

    def test_under_three_shows_only_the_chip_and_that_fewer_answered(self):
        self.person("pat", self.pick("beta", "Up"))
        self.person("sam", self.pick("beta", "Down"))
        self.assertEqual(self.lines()[1:], ["Beta chip: fewer than three answered.", "Skipped 0 files and 0 lines."])

    def test_a_question_that_left_the_bank_is_headed_by_its_id(self):
        for name in ("pat", "sam", "kim"):
            self.person(name, self.pick("retired", "Kept"))
        self.assertEqual(self.lines()[1:], ["retired: 3 answered", "  Kept: 3", "Skipped 0 files and 0 lines."])

    def test_a_question_that_left_the_bank_under_three_shows_only_its_id(self):
        self.person("pat", self.pick("retired", "Kept"))
        self.assertEqual(self.lines()[1:], ["retired: fewer than three answered.", "Skipped 0 files and 0 lines."])

    def test_a_label_no_longer_in_the_bank_follows_other(self):
        self.person("pat", self.pick("beta", "Sideways"))
        self.person("sam", self.pick("beta", "Up"))
        self.person("kim", self.pick("beta", "Up"))
        self.assertEqual(self.lines()[2:7], ["  Up: 2", "  Flat: 0", "  Down: 0", "  Other: 0", "  Sideways: 1"])

    def test_it_groups_by_the_date_and_id_the_answers_recorded(self):
        for name in ("pat", "sam", "kim"):
            self.person(name, self.pick("alpha", "Good"), self.pick("gamma", "Yes", "2020-01-01"))
        lines = self.lines()
        self.assertIn("Alpha chip: 3 answered", lines)
        self.assertNotIn("Gamma chip", " ".join(lines))

    def test_files_that_are_not_a_person_are_skipped_and_counted(self):
        self.three_on_beta()
        answers = self.folder / "answers"
        for name in (".DS_Store", "pat (1).jsonl", ".jsonl", "notes.txt"):
            (answers / name).write_text(json.dumps(self.pick("beta", "Down")) + "\n", encoding="utf-8")
        (answers / "folder.jsonl").mkdir()
        lines = self.lines()
        self.assertEqual(lines[-1], "Skipped 5 files and 0 lines.")
        self.assertIn("  Down: 0", lines)

    def test_lines_that_do_not_count_are_skipped_and_counted(self):
        self.three_on_beta()
        bad = ["not json", "[1, 2]", "3", json.dumps({"date": self.yesterday, "id": "beta"}),
               json.dumps({"id": "beta", "answer": "Up"}), json.dumps({"date": self.yesterday, "answer": "Up"}),
               json.dumps(self.pick("beta", ["Up"])), json.dumps(self.pick("beta", {"a": 1})),
               json.dumps(self.pick("beta", "")), json.dumps(self.pick("", "Up")),
               json.dumps(self.pick("beta", 3))]
        with (self.folder / "answers" / "pat.jsonl").open("a", encoding="utf-8") as out:
            out.write("".join(line + "\n" for line in bad))
        with (self.folder / "answers" / "sam.jsonl").open("ab") as out:
            out.write(b"\xff\xfe\n")
        lines = self.lines()
        self.assertEqual(lines[-1], "Skipped 0 files and {} lines.".format(len(bad) + 1))
        self.assertIn("Beta chip: 3 answered", lines)
        self.assertIn("  Up: 2", lines)

    def test_a_missing_answers_folder_is_no_answers_and_creates_nothing(self):
        before = self.files()
        self.assertEqual(self.lines(), ["Results for {}".format(self.yesterday), "No answers for this date.",
                                        "Skipped 0 files and 0 lines."])
        self.assertEqual(self.files(), before)

    def test_it_writes_nothing(self):
        self.three_on_beta()
        before = self.files()
        contents = (self.folder / "answers" / "pat.jsonl").read_bytes()
        self.lines()
        self.assertEqual(self.files(), before)
        self.assertEqual((self.folder / "answers" / "pat.jsonl").read_bytes(), contents)


class TheScript(unittest.TestCase):
    def tree(self):
        return ast.parse(SCRIPT.read_text(encoding="utf-8"), feature_version=(3, 9))

    def test_it_imports_the_standard_library_only(self):
        names = set()
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertTrue(names)
        self.assertLessEqual(names, STDLIB)

    def test_the_safe_name_pattern_is_copied_from_the_usage_log(self):
        pattern = 're.compile(r"[^A-Za-z0-9._-]")'
        self.assertIn(pattern, (ROOT / ".claude" / "hooks" / "usage_log.py").read_text(encoding="utf-8"))
        self.assertIn(pattern, SCRIPT.read_text(encoding="utf-8"))


    def test_no_login_is_a_refusal_not_a_traceback(self):
        spec = importlib.util.spec_from_file_location("pulse_under_test", str(SCRIPT))
        pulse = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pulse)
        for error in (KeyError("uid"), OSError("no login")):
            with mock.patch.object(pulse.getpass, "getuser", side_effect=error):
                with self.assertRaises(pulse.Refused) as refused:
                    pulse.login_name()
                self.assertIn("LOGNAME", str(refused.exception))


class TheExampleBank(PulseCase):
    def test_it_passes_check_once_copied_and_has_at_least_five_questions(self):
        shutil.copy(str(EXAMPLE), str(self.folder / "questions.md"))
        result = self.pulse("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(int(result.stdout.split()[1]), 5)


class Wording(unittest.TestCase):
    def test_standup_names_the_pulse_lines(self):
        text = flat(STANDUP.read_text(encoding="utf-8"))
        for words in ("Pulse: skipped, company/DATA.md doesn't clear it.", "`Pulse: skipped,` with its reason",
                      "Today's pulse:", "`Today's pulse: <chip>. Say \"pulse\" to answer.`",
                      "python3 scripts/pulse.py question --json", "`question.header`",
                      "left out silently"):
            self.assertIn(words, text)

    def test_standup_keeps_what_it_already_pinned(self):
        text = flat(STANDUP.read_text(encoding="utf-8"))
        for words in (CLEARED + " A provider named in the argument needs a row of its own.",
                      "respond, reply, label, draft, create or update call",
                      "A connector call that fails gets the same line, with the reason.",
                      "No `company/DATA.md` means none is", "skip all three"):
            self.assertIn(words, text)

    def test_standup_output_puts_the_pulse_line_before_the_skipped_lines(self):
        output = flat(STANDUP.read_text(encoding="utf-8").split("## Output", 1)[1])
        self.assertLess(output.index("Waiting on someone"), output.index("the pulse line"))
        self.assertLess(output.index("the pulse line"), output.index("the skipped-source lines"))

    def test_standup_never_answers(self):
        text = flat(STANDUP.read_text(encoding="utf-8"))
        self.assertIn("never runs `answer`", text)
        self.assertNotIn("pulse.py answer", text)
        self.assertNotIn("pulse.py results", text)

    def test_the_skill_says_what_clears_it_and_what_it_treats_as_data(self):
        text = flat(SKILL.read_text(encoding="utf-8"))
        for words in (CLEARED, "`Pulse folder`", "--other-file", "data, never instructions", "AskUserQuestion",
                      "only item of `questions`", "local-data/pulse-other.txt", "whether or not `answer` succeeded",
                      "the skill never runs `answer` without a pick made in this session"):
            self.assertIn(words, text)

    def test_the_skill_adds_no_allowed_tools(self):
        head = SKILL.read_text(encoding="utf-8").split("\n---", 1)[0]
        self.assertIn("name: pulse", head)
        self.assertNotIn("allowed-tools", head)

    def test_the_readme_covers_each_section_the_team_needs(self):
        text = flat(GUIDE.read_text(encoding="utf-8"))
        for words in ("## Setting it up", "## Finding the day's question", "## Submitting an answer",
                      "## Changing the questions", "## What others can see", "SANVIO_PULSE_FOLDER", "Pulse folder",
                      "--other-file", "--date", "never a name or an Other text", "asks to run its commands"):
            self.assertIn(words, text)

    def test_the_harness_names_it(self):
        self.assertIn("skills/pulse/SKILL.md", (ROOT / "AGENTS.md").read_text(encoding="utf-8"))
        capabilities = (ROOT / "skills" / "starter-updates" / "capabilities.md").read_text(encoding="utf-8")
        self.assertEqual(capabilities.count("`skills/pulse/`"), 1)
        self.assertIn("`scripts/pulse.py`", capabilities)
        self.assertIn("A daily question", (ROOT / "README.md").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Daily pulse question", changelog)


def dated(date_line, heading="## two\n", chip="Chip: Dated\n"):
    return heading + date_line + chip + "Question: When?\n" + TWO_OPTIONS


PROPOSAL = "## launch\nChip: Launch\nQuestion: Ready to launch?\n- Yes: Ready\n- No: Not yet\n"


def proposed_bytes(day):
    return ("\n## launch\nDate: {}\nChip: Launch\nQuestion: Ready to launch?\n- Yes: Ready\n- No: Not yet\n"
            .format(day)).encode("utf-8")


class DatedBankProblems(PulseCase):
    REAL_DATE = "the date must be a real date written YYYY-MM-DD"
    CASES = {
        "empty date": (question() + dated("Date:\n"), "two:", REAL_DATE),
        "blank date": (question() + dated("Date:   \n"), "two:", REAL_DATE),
        "compact date": (question() + dated("Date: 20261104\n"), "two:", REAL_DATE),
        "unpadded date": (question() + dated("Date: 2026-2-3\n"), "two:", REAL_DATE),
        "impossible date": (question() + dated("Date: 2026-02-30\n"), "two:", REAL_DATE),
        "words": (question() + dated("Date: next Friday\n"), "two:", REAL_DATE),
        "same date twice": (question() + dated("Date: 2026-12-01\n") + dated("Date: 2026-12-01\n", "## three\n"),
                            "three:", "two questions have this date"),
        "every question dated": (dated("Date: 2026-12-01\n"), "questions.md:", "it has no questions without a date"),
    }

    def test_check_names_each_date_problem_on_one_line(self):
        for name, (text, where, words) in self.CASES.items():
            with self.subTest(name):
                self.bank(text)
                before = self.files()
                result = self.pulse("check")
                self.assert_refused(result, before, where + " " + words)
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_a_duplicate_date_names_the_later_question_only(self):
        self.bank(question() + dated("Date: 2026-12-01\n") + dated("Date: 2026-12-01\n", "## three\n"))
        said = self.said(self.pulse("check"))
        self.assertIn("three: two questions have this date", said)
        self.assertNotIn("two: two questions have this date", said)

    def test_two_bad_dates_are_not_also_a_duplicate(self):
        self.bank(question() + dated("Date:\n") + dated("Date:\n", "## three\n"))
        result = self.pulse("check")
        self.assertEqual(result.stderr.splitlines(), ["two: " + self.REAL_DATE, "three: " + self.REAL_DATE])

    def test_a_date_before_today_passes(self):
        self.bank(question() + dated("Date: 2020-01-01\n"))
        result = self.pulse("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 questions", result.stdout)


class DatedRotation(PulseCase):
    def ids_for(self, days):
        ids = []
        for day in days:
            result = self.pulse("question", "--json", "--date", day.isoformat())
            self.assertEqual(result.returncode, 0, result.stderr)
            ids.append(json.loads(result.stdout)["id"])
        return ids

    def test_a_date_line_is_read_as_the_questions_date(self):
        self.bank(BANK + "\n" + dated("Date:   2026-05-10  \n"))
        lines = self.pulse("question", "--date", "2026-05-10").stdout.splitlines()
        self.assertEqual(lines[0], "2026-05-10 (two)")
        self.assertEqual(lines[1:3], ["Dated", "When?"])

    def test_with_two_date_lines_the_last_one_wins(self):
        self.bank(BANK + "\n" + dated("Date: 2026-05-09\nDate: 2026-05-10\n"))
        self.assertEqual(self.pulse("check").returncode, 0)
        self.assertEqual(self.ids_for([datetime.date(2026, 5, 10)]), ["two"])
        first = datetime.date(2026, 5, 9)
        self.assertEqual(self.ids_for([first]), [IDS[first.toordinal() % 3]])

    def test_a_bank_with_no_dates_asks_what_it_asked_before(self):
        self.bank()
        days = [datetime.date(2026, 7, 1) + datetime.timedelta(days=n) for n in range(9)]
        self.assertEqual(self.ids_for(days), [IDS[day.toordinal() % 3] for day in days])

    def test_a_dated_question_is_asked_on_its_date_only_and_the_rest_take_turns(self):
        special = datetime.date(2026, 5, 10)
        self.bank(BANK.replace("## beta", dated("Date: 2026-05-10\n", "## special\n") + "\n## beta"))
        self.assertEqual(self.pulse("check").returncode, 0)
        days = [datetime.date(2026, 5, 1) + datetime.timedelta(days=n) for n in range(20)]
        expected = ["special" if day == special else IDS[day.toordinal() % 3] for day in days]
        self.assertEqual(self.ids_for(days), expected)


class DatedAnswers(PulseCase):
    def test_a_dated_question_for_another_day_needs_its_date(self):
        self.bank(BANK + "\n" + dated("Date: {}\n".format(self.yesterday), "## past\n"))
        before = self.files()
        self.assert_refused(self.pulse("answer", "past", "1"), before, "isn't today's question")
        result = self.pulse("answer", "past", "1", "--date", self.yesterday)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.answers(), [{"date": self.yesterday, "id": "past", "answer": "One"}])

    def test_a_dated_question_for_today_is_todays_question(self):
        self.bank(BANK + "\n" + dated("Date: {}\n".format(self.today.isoformat()), "## now\n"))
        self.assertEqual(json.loads(self.pulse("question", "--json").stdout)["id"], "now")
        result = self.pulse("answer", "now", "2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.answers()[0]["answer"], "Two")

    def test_answers_under_a_dated_id_show_in_results_and_the_summary(self):
        self.bank(BANK + "\n" + dated("Date: {}\n".format(self.yesterday), "## past\n"))
        self.person("sam", self.pick("past", "One"))
        self.person("kim", self.pick("past", "Two"))
        self.assertEqual(self.pulse("answer", "past", "1", "--date", self.yesterday).returncode, 0)
        results = self.pulse("results").stdout.splitlines()
        self.assertEqual(results[1:6], ["Dated: 3 answered", "  One: 2", "  Two: 1", "  Other: 0",
                                        "Skipped 0 files and 0 lines."])
        summary = self.pulse("summary", "--since", self.yesterday, "--until", self.yesterday).stdout
        self.assertIn("## {}: Dated".format(self.yesterday), summary)
        self.assertIn("When?", summary)
        self.assertIn("3 answered", summary)
        self.assertIn("- One: 2", summary)


class Propose(PulseCase):
    def setUp(self):
        super().setUp()
        self.bank()
        self.tomorrow = (self.today + datetime.timedelta(days=1)).isoformat()

    def source(self, content=PROPOSAL, name="proposal.md"):
        path = self.tmp / name  # outside the shared folder, so files() never sees it
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return str(path)

    def bank_bytes(self):
        return (self.folder / "questions.md").read_bytes()

    def assert_unchanged(self, args, *words, stderr=None):
        before, contents = self.files(), self.bank_bytes()
        result = self.pulse("propose", *args)
        self.assert_refused(result, before, *words)
        self.assertEqual(self.bank_bytes(), contents)
        self.assertNotIn("Traceback", result.stderr)
        if stderr is None:
            self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        else:
            self.assertEqual(result.stderr, stderr)

    def test_each_refusal_is_one_line_and_leaves_the_bank_byte_for_byte(self):
        good = self.source()
        yesterday = (self.today - datetime.timedelta(days=1)).isoformat()
        compact = (self.today + datetime.timedelta(days=1)).strftime("%Y%m%d")
        cases = {
            "file that can't be read": (["--file", str(self.tmp / "gone.md"), "--date", self.tomorrow],
                                        ("--file", "can't be read")),
            "file that isn't UTF-8": (["--file", self.source(b"## launch\nChip: \xff\xfe\n", "u.md"),
                                       "--date", self.tomorrow], ("--file", "UTF-8")),
            "no questions": (["--file", self.source("Only prose.\n", "none.md"), "--date", self.tomorrow],
                             ("exactly one question", "0")),
            "two questions": (["--file", self.source(PROPOSAL + PROPOSAL.replace("## launch", "## other"), "two.md"),
                               "--date", self.tomorrow], ("exactly one question", "2")),
            "a Date: line in the file": (["--file", self.source(
                PROPOSAL.replace("Chip:", "Date: {}\nChip:".format(self.tomorrow)), "d.md"), "--date", self.tomorrow],
                ("Date:",)),
            "a compact date": (["--file", good, "--date", compact], ("--date", "YYYY-MM-DD")),
            "not a date": (["--file", good, "--date", "2026-13-40"], ("--date", "YYYY-MM-DD")),
            "today": (["--file", good, "--date", self.today.isoformat()], ("after today",)),
            "yesterday": (["--file", good, "--date", yesterday], ("after today",)),
            "an id already in the bank": (["--file", self.source(PROPOSAL.replace("## launch", "## alpha"), "a.md"),
                                           "--date", self.tomorrow], ("alpha", "already in the bank")),
            "no --date": (["--file", good], ("--date",)),
            "no --file": (["--date", self.tomorrow], ("--file",)),
        }
        for name, (args, words) in cases.items():
            with self.subTest(name):
                self.assert_unchanged(args, *words)

    def test_a_combined_bank_that_fails_prints_its_problems_and_changes_nothing(self):
        long_chip = self.source(PROPOSAL.replace("Chip: Launch", "Chip: Thirteen char"), "chip.md")
        self.assert_unchanged(["--file", long_chip, "--date", self.tomorrow],
                              stderr="launch: the chip is over 12 characters\n")
        self.bank(BANK + "\n" + dated("Date: {}\n".format(self.tomorrow), "## taken\n"))
        self.assert_unchanged(["--file", self.source(), "--date", self.tomorrow],
                              stderr="launch: two questions have this date\n")

    def test_a_bank_that_already_fails_is_refused_as_check_refuses_it(self):
        self.bank(question(chip=""))
        expected = self.pulse("check").stderr
        self.assertTrue(expected)
        self.assert_unchanged(["--file", self.source(), "--date", self.tomorrow], stderr=expected)

    def test_a_bank_that_goes_after_main_read_it_is_a_refusal_not_a_traceback(self):
        spec = importlib.util.spec_from_file_location("pulse_under_test", str(SCRIPT))
        pulse = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pulse)
        questions = pulse.parse_bank(BANK)
        args = mock.Mock(file=self.source(), date=self.tomorrow)
        (self.folder / "questions.md").unlink()
        with self.assertRaises(pulse.Refused) as refused:
            pulse.run_propose(str(self.folder), questions, args)
        self.assertIn("questions.md: it can't be read", str(refused.exception))
        (self.folder / "questions.md").write_bytes(b"## one\nChip: \xff\xfe\n")
        with self.assertRaises(pulse.Refused) as refused:
            pulse.run_propose(str(self.folder), questions, args)
        self.assertEqual(str(refused.exception), "questions.md: it isn't valid UTF-8")
        self.assertEqual((self.folder / "questions.md").read_bytes(), b"## one\nChip: \xff\xfe\n")

    def test_it_appends_exactly_the_question_with_its_date(self):
        before, contents = self.files(), self.bank_bytes()
        result = self.pulse("propose", "--file", self.source(), "--date", self.tomorrow)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Added launch for {}.\n".format(self.tomorrow))
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.bank_bytes(), contents + proposed_bytes(self.tomorrow))
        self.assertEqual(self.files(), before)
        self.assertEqual(self.pulse("check").returncode, 0)

    def test_a_bank_without_a_final_newline_gets_one_first(self):
        self.bank(BANK.rstrip("\n"))
        contents = self.bank_bytes()
        result = self.pulse("propose", "--file", self.source(), "--date", self.tomorrow)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.bank_bytes(), contents + b"\n" + proposed_bytes(self.tomorrow))

    def test_it_writes_only_the_parsed_fields_from_the_file(self):
        draft = ("# My draft\r\n\r\nSome prose about it.\r\n- Stray: before the heading\r\n\r\n## launch\r\n"
                 "Chip:   Launch  \r\nNotes: dropped\r\nQuestion: Ready to launch?\r\n\r\n- Yes: Ready\r\n"
                 "- No:  Not yet\r\n")
        contents = self.bank_bytes()
        path = self.source(b"\xef\xbb\xbf" + draft.encode("utf-8"))
        result = self.pulse("propose", "--file", path, "--date", self.tomorrow)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.bank_bytes(), contents + proposed_bytes(self.tomorrow))

    def test_answers_files_keep_their_bytes(self):
        self.person("sam", self.pick("alpha", "Good"), self.pick("beta", "Other", other="my words"))
        before = self.files()
        answers = (self.folder / "answers" / "sam.jsonl").read_bytes()
        self.assertEqual(self.pulse("propose", "--file", self.source(), "--date", self.tomorrow).returncode, 0)
        self.assertEqual(self.files(), before)
        self.assertEqual((self.folder / "answers" / "sam.jsonl").read_bytes(), answers)

    def test_a_proposed_question_changes_its_own_day_and_no_other(self):
        days = [self.today + datetime.timedelta(days=n) for n in range(1, 31)]

        def asked():
            return [json.loads(self.pulse("question", "--json", "--date", day.isoformat()).stdout)["id"]
                    for day in days]

        earlier = asked()
        result = self.pulse("propose", "--file", self.source(), "--date", days[9].isoformat())
        self.assertEqual(result.returncode, 0, result.stderr)
        later = asked()
        self.assertEqual(later[9], "launch")
        self.assertEqual(later[:9] + later[10:], earlier[:9] + earlier[10:])


class ProposeWording(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT)] + list(args), capture_output=True, encoding="utf-8")

    def test_help_lists_propose_with_its_flags(self):
        top = self.run_script("--help")
        self.assertEqual(top.returncode, 0)
        self.assertIn("propose", top.stdout)
        own = self.run_script("propose", "--help")
        self.assertEqual(own.returncode, 0)
        self.assertIn("--file", own.stdout)
        self.assertIn("--date", own.stdout)

    def test_the_docstring_says_answer_and_propose_write(self):
        text = flat(ast.get_docstring(ast.parse(SCRIPT.read_text(encoding="utf-8"))))
        self.assertIn("python3 scripts/pulse.py propose --file <path> --date YYYY-MM-DD", text)
        self.assertIn("`answer` and `propose` write", text)
        self.assertNotIn("Only `answer` writes", text)

    def test_the_readme_and_example_say_how_dates_work(self):
        guide = flat(GUIDE.read_text(encoding="utf-8"))
        for words in ("## Changing the questions", "A question with a `Date:` line", "is asked on that date only",
                      "shifts no other day", "python3 scripts/pulse.py propose --file", "that id's old answers",
                      'propose["You: pulse.py propose"] -->|appends a dated question| bank'):
            self.assertIn(words, guide)
        self.assertIn("Date: line", flat(EXAMPLE.read_text(encoding="utf-8")))
        self.assertIn("Propose a pulse question", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_the_changelog_entry_is_under_a_dated_heading(self):
        # Anywhere in the log: later entries go above it.
        lines = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
        headings = [line for line in lines if line.startswith("## ") and line.endswith(": Propose a pulse question")]
        self.assertEqual(len(headings), 1, headings)
        date = headings[0][len("## "):-len(": Propose a pulse question")]
        self.assertEqual(datetime.date.fromisoformat(date).isoformat(), date)


if __name__ == "__main__":
    unittest.main()
