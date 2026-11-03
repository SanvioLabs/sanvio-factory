#!/usr/bin/env python3
"""A team's daily multiple-choice question, kept in a shared synced folder.

    python3 scripts/pulse.py check                                   # is the bank well formed?
    python3 scripts/pulse.py question [--date YYYY-MM-DD] [--json]   # the day's question
    python3 scripts/pulse.py answer <id> <number> [--date YYYY-MM-DD]
    python3 scripts/pulse.py answer <id> --other-file <path> [--date YYYY-MM-DD]
    python3 scripts/pulse.py results [--date YYYY-MM-DD]             # counts for a day, yesterday by default
    python3 scripts/pulse.py summary [--since YYYY-MM-DD] [--until YYYY-MM-DD]  # Markdown for a period, 14 days by default
    python3 scripts/pulse.py propose --file <path> --date YYYY-MM-DD  # add a question for one date

The folder comes from HARNESS_PULSE_FOLDER. It holds questions.md, the bank, and
answers/<login>.jsonl, one file per person.
`answer` and `propose` write: `answer` only to that person's file, and `propose`
only to the end of questions.md. skills/pulse/ is the procedure and says who may
read what.
Refusals and problems go to stderr with exit 1, and success goes to stdout.
"""
import argparse
import collections
import datetime
import getpass
import json
import os
import re
import sys

BANK = "questions.md"
ANSWERS = "answers"
OTHER = "Other"
MAX_CHIP = 12
MIN_OPTIONS = 2
MAX_OPTIONS = 4
MIN_TO_SHOW = 3
SUMMARY_DAYS = 14
QUESTION_ID = re.compile(r"[a-z0-9-]+")
NUMBER = re.compile(r"[0-9]+")
PERSON_FILE = re.compile(r"[A-Za-z0-9._-]+\.jsonl")
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")  # the same pattern as .claude/hooks/usage_log.py, copied
HOW_TO_SET = 'Set it in your shell profile: export HARNESS_PULSE_FOLDER="/path/to/the/shared/folder"'


class Refused(Exception):
    """A one-line reason to stop, having written nothing."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print("pulse: {}".format(message), file=sys.stderr)
        sys.exit(1)


def pulse_folder():
    folder = os.environ.get("HARNESS_PULSE_FOLDER", "")
    if not folder:
        raise Refused("HARNESS_PULSE_FOLDER isn't set. " + HOW_TO_SET)
    if not os.path.isdir(folder):
        raise Refused("HARNESS_PULSE_FOLDER names a folder that doesn't exist: {}. {}".format(folder, HOW_TO_SET))
    return folder


def parse_bank(text):
    """The questions in file order. Anything that isn't part of a question is ignored."""
    questions = []
    current = None
    for line in text.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("## "):
            current = {"id": line[3:].strip(), "date": "", "has_date": False, "chip": "", "question": "",
                       "options": []}
            questions.append(current)
        elif current is None:
            continue
        elif line.startswith("Date:"):
            current["date"] = line[len("Date:"):].strip()
            current["has_date"] = True  # an empty Date: line is a problem, and no Date: line isn't
        elif line.startswith("Chip:"):
            current["chip"] = line[len("Chip:"):].strip()
        elif line.startswith("Question:"):
            current["question"] = line[len("Question:"):].strip()
        elif line.startswith("- "):
            label, _, description = line[2:].partition(":")
            current["options"].append((label.strip(), description.strip()))
    return questions


def bank_problems(questions):
    """Every problem in the bank, one line each, each starting with its question's id."""
    if not questions:
        return ["{}: it has no questions".format(BANK)]
    found = []
    seen = set()
    dates = set()
    for question in questions:
        name = question["id"] or "(no id)"
        if not QUESTION_ID.fullmatch(question["id"]):
            found.append("{}: the id must be lowercase letters, digits and hyphens".format(name))
        if question["id"] in seen:
            found.append("{}: two questions have this id".format(name))
        seen.add(question["id"])
        if question["has_date"]:
            if recorded_day(question["date"]) is None:
                found.append("{}: the date must be a real date written YYYY-MM-DD".format(name))
            elif question["date"] in dates:
                found.append("{}: two questions have this date".format(name))
            else:
                dates.add(question["date"])
        if not question["chip"]:
            found.append("{}: the chip is missing or empty".format(name))
        elif len(question["chip"]) > MAX_CHIP:
            found.append("{}: the chip is over {} characters".format(name, MAX_CHIP))
        if not question["question"]:
            found.append("{}: the question is missing or empty".format(name))
        options = question["options"]
        if len(options) < MIN_OPTIONS:
            found.append("{}: it has fewer than {} options".format(name, MIN_OPTIONS))
        elif len(options) > MAX_OPTIONS:
            found.append("{}: it has more than {} options".format(name, MAX_OPTIONS))
        labels = collections.Counter(label for label, _ in options)
        for place, (label, description) in enumerate(options, 1):
            if not label:
                found.append("{}: option {} has no label".format(name, place))
            if not description:
                found.append("{}: option {} has no description".format(name, place))
            if label == OTHER:
                found.append("{}: an option is labelled {}, which the window adds itself".format(name, OTHER))
        for label, count in labels.items():
            if label and count > 1:
                found.append("{}: two options have the label {}".format(name, label))
    if all(question["date"] for question in questions):
        found.append("{}: it has no questions without a date".format(BANK))
    return found


def read_bank(folder):
    """(questions, problems) for the bank in this folder."""
    path = os.path.join(folder, BANK)
    if not os.path.isfile(path):
        return [], ["{}: there is no {} in the folder".format(BANK, BANK)]
    try:
        with open(path, "rb") as bank:
            text = bank.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["{}: it isn't valid UTF-8".format(BANK)]
    except OSError as error:
        return [], ["{}: it can't be read ({})".format(BANK, error.strerror)]
    questions = parse_bank(text)
    return questions, bank_problems(questions)


def chosen_day(value, default, flag="--date"):
    if value is None:
        return default
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise Refused("{} must be a real date written YYYY-MM-DD, not {}".format(flag, value))


def day_question(questions, day):
    """The question dated this day, or else the undated questions taking turns in file order."""
    for question in questions:
        if question["date"] == day.isoformat():
            return question
    undated = [question for question in questions if not question["date"]]
    return undated[day.toordinal() % len(undated)]


def login_name():
    try:
        login = getpass.getuser()
    except (KeyError, OSError):  # no login variable and no account entry: KeyError before Python 3.13
        raise Refused("pulse can't tell your login: set LOGNAME or USER")
    return SAFE_NAME.sub("_", login) or "unknown"


def parse_answer_line(raw):
    """The record on this line of an answers file, or None if the line doesn't count."""
    try:
        record = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):  # undecodable bytes are a ValueError too
        return None
    if not isinstance(record, dict):
        return None
    for key in ("date", "id", "answer"):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            return None
    return record


def read_answers(path):
    """(records, how many lines were skipped) for one person's file."""
    with open(path, "rb") as answers:
        lines = answers.read().split(b"\n")
    if not lines[-1]:
        lines.pop()
    records = [parse_answer_line(raw) for raw in lines]
    kept = [record for record in records if record is not None]
    return kept, len(records) - len(kept)


def my_last_answer(folder, day, question_id):
    path = os.path.join(folder, ANSWERS, login_name() + ".jsonl")
    if not os.path.isfile(path):
        return None
    answered = None
    for record in read_answers(path)[0]:
        if record["date"] == day.isoformat() and record["id"] == question_id:
            answered = record["answer"]
    return answered


def run_check(folder, questions, args):
    count = len(questions)
    print("{}: {} question{}, no problems.".format(BANK, count, "" if count == 1 else "s"))
    return 0


def run_question(folder, questions, args):
    day = chosen_day(args.date, datetime.date.today())
    question = day_question(questions, day)
    if args.json:
        print(json.dumps({
            "date": day.isoformat(),
            "id": question["id"],
            "answered": my_last_answer(folder, day, question["id"]),
            "question": {
                "question": question["question"],
                "header": question["chip"],
                "multiSelect": False,
                "options": [{"label": label, "description": description}
                            for label, description in question["options"]],
            },
        }))
        return 0
    # The id is here too because `answer` takes it.
    print("{} ({})".format(day.isoformat(), question["id"]))
    print(question["chip"])
    print(question["question"])
    for place, (label, description) in enumerate(question["options"], 1):
        print("{}. {}: {}".format(place, label, description))
    return 0


def read_other_file(path):
    try:
        with open(path, "rb") as other:
            text = other.read().decode("utf-8").strip()
    except OSError as error:
        raise Refused("--other-file can't be read: {}".format(error.strerror))
    except UnicodeDecodeError:
        raise Refused("--other-file isn't valid UTF-8")
    if not text:
        raise Refused("--other-file is empty")
    return text


def run_answer(folder, questions, args):
    today = datetime.date.today()
    day = chosen_day(args.date, today)
    question = next((q for q in questions if q["id"] == args.id), None)
    if question is None:
        raise Refused("{} isn't in the bank".format(args.id))
    if args.date is None and question is not day_question(questions, today):
        raise Refused("{} isn't today's question. Use --date for a day you missed".format(args.id))
    if day > today:
        raise Refused("--date is after today: {}".format(day.isoformat()))
    if (args.number is None) == (args.other_file is None):
        raise Refused("give one of an option's number or --other-file")
    record = {"date": day.isoformat(), "id": question["id"]}
    if args.other_file is not None:
        record["answer"] = OTHER
        record["other"] = read_other_file(args.other_file)
    else:
        places = [str(place) for place in range(1, len(question["options"]) + 1)]
        if not NUMBER.fullmatch(args.number) or args.number not in places:
            raise Refused("{} isn't one of that question's options: 1 to {}".format(args.number, len(places)))
        record["answer"] = question["options"][int(args.number) - 1][0]
    answers = os.path.join(folder, ANSWERS)
    os.makedirs(answers, exist_ok=True)
    with open(os.path.join(answers, login_name() + ".jsonl"), "a", encoding="utf-8") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("Recorded {} for {} on {}.".format(record["answer"], record["id"], record["date"]))
    return 0


def everyones_records(folder):
    """(one list of records per person, files skipped, lines skipped), holding no file name."""
    people = []
    files = lines = 0
    answers = os.path.join(folder, ANSWERS)
    if not os.path.isdir(answers):
        return people, files, lines
    for name in sorted(os.listdir(answers)):
        path = os.path.join(answers, name)
        if not PERSON_FILE.fullmatch(name) or not os.path.isfile(path):
            files += 1
            continue
        try:
            records, bad = read_answers(path)
        except OSError:
            files += 1
            continue
        lines += bad
        people.append(records)
    return people, files, lines


def tally(folder, day):
    """({question id: each person's last label}, files skipped, lines skipped) for one date."""
    people, files, lines = everyones_records(folder)
    picks = {}
    for records in people:
        last = {record["id"]: record["answer"] for record in records if record["date"] == day}
        for question_id, label in last.items():
            picks.setdefault(question_id, []).append(label)
    return picks, files, lines


def counted(count, noun):
    return "{} {}{}".format(count, noun, "" if count == 1 else "s")


def skipped_line(files, lines):
    return "Skipped {} and {}.".format(counted(files, "file"), counted(lines, "line"))


def labels_in_order(question, counts):
    """The bank's options with zeros, Other, then labels it doesn't know. Sorted if it has left the bank."""
    if not question:
        return sorted(counts)
    shown = [label for label, _ in question["options"]] + [OTHER]
    return shown + sorted(set(counts) - set(shown))


def run_results(folder, questions, args):
    day = chosen_day(args.date, datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    picks, files, lines = tally(folder, day)
    bank = {question["id"]: question for question in questions}
    print("Results for {}".format(day))
    order = [question["id"] for question in questions if question["id"] in picks]
    order += sorted(question_id for question_id in picks if question_id not in bank)
    if not order:
        print("No answers for this date.")
    for question_id in order:
        question = bank.get(question_id)
        heading = question["chip"] if question else question_id
        labels = picks[question_id]
        if len(labels) < MIN_TO_SHOW:
            print("{}: fewer than three answered.".format(heading))
            continue
        print("{}: {} answered".format(heading, len(labels)))
        counts = collections.Counter(labels)
        for label in labels_in_order(question, counts):
            print("  {}: {}".format(label, counts[label]))
    print(skipped_line(files, lines))
    return 0


def one_line(text):
    """Text from an answers file, unable to start a Markdown line of its own."""
    return " ".join(text.split())


def recorded_day(value):
    """The date in a record's date field, or None unless it's a real YYYY-MM-DD."""
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError:
        return None
    return day if day.isoformat() == value else None  # newer Pythons also take 20261031


def print_summary_entry(date, question_id, question, records):
    print()
    print("## {}: {}".format(date, question["chip"] if question else one_line(question_id)))
    if len(records) < MIN_TO_SHOW:
        print("Fewer than three answered.")
        return
    if question:
        print(question["question"])
    print()
    print("{} answered".format(len(records)))
    print()
    counts = collections.Counter(record["answer"] for record in records)
    for label in labels_in_order(question, counts):
        print("- {}: {}".format(one_line(label), counts[label]))
    written = [record["other"] for record in records
               if record["answer"] == OTHER and isinstance(record.get("other"), str)]
    others = sorted(text for text in map(one_line, written) if text)  # sorted, so the order can't point at a file
    if others:
        print()
        print("Other answers:")
        print()
        for text in others:
            print("- {}".format(text))


def run_summary(folder, questions, args):
    until = chosen_day(args.until, datetime.date.today(), "--until")
    earliest = datetime.date.fromordinal(max(1, until.toordinal() - (SUMMARY_DAYS - 1)))
    since = chosen_day(args.since, earliest, "--since")
    if until < since:
        raise Refused("--until is before --since: {} is before {}".format(until.isoformat(), since.isoformat()))
    people, files, lines = everyones_records(folder)
    picks = {}
    for records in people:
        last = {(record["date"], record["id"]): record for record in records}
        for key, record in last.items():
            day = recorded_day(key[0])
            if day is not None and since <= day <= until:
                picks.setdefault(key, []).append(record)
    bank = {question["id"]: question for question in questions}
    print("# Pulse summary: {} to {}".format(since.isoformat(), until.isoformat()))
    if not picks:
        print()
        print("No answers for this period.")
    for date, question_id in sorted(picks):
        print_summary_entry(date, question_id, bank.get(question_id), picks[(date, question_id)])
    print()
    print(skipped_line(files, lines))
    return 0


def read_proposal(path):
    """The one question in the --file at this path, which has no Date: line of its own."""
    try:
        with open(path, "rb") as source:
            text = source.read().decode("utf-8-sig")
    except OSError as error:
        raise Refused("--file can't be read: {}".format(error.strerror))
    except UnicodeDecodeError:
        raise Refused("--file isn't valid UTF-8")
    proposed = parse_bank(text)
    if len(proposed) != 1:
        raise Refused("--file must hold exactly one question, and it holds {}".format(len(proposed)))
    if proposed[0]["has_date"]:
        raise Refused("--file has a Date: line. Leave it out and give the date with --date")
    return proposed[0]


def run_propose(folder, questions, args):
    question = read_proposal(args.file)
    day = recorded_day(args.date)
    if day is None:
        raise Refused("--date must be a real date written YYYY-MM-DD, not {}".format(args.date))
    if day <= datetime.date.today():
        raise Refused("--date must be after today, not {}".format(day.isoformat()))
    if any(other["id"] == question["id"] for other in questions):
        raise Refused("{} is already in the bank".format(question["id"]))
    path = os.path.join(folder, BANK)
    try:  # main() read it a moment ago, but it can go or change in between
        with open(path, "rb") as bank:
            current = bank.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Refused("{}: it isn't valid UTF-8".format(BANK))
    except OSError as error:
        raise Refused("{}: it can't be read ({})".format(BANK, error.strerror))
    lines =["", "## " + question["id"], "Date: " + day.isoformat(), "Chip: " + question["chip"],
             "Question: " + question["question"]]
    lines += ["- {}: {}".format(label, description) for label, description in question["options"]]
    appended = ("" if current.endswith("\n") else "\n") + "".join(line + "\n" for line in lines)
    problems = bank_problems(parse_bank(current + appended))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    with open(path, "a", encoding="utf-8", newline="") as out:
        out.write(appended)
    print("Added {} for {}.".format(question["id"], day.isoformat()))
    return 0


def build_parser():
    parser = Parser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="list each problem in the bank")
    question = commands.add_parser("question", help="print the day's question")
    question.add_argument("--date", help="another day, YYYY-MM-DD")
    question.add_argument("--json", action="store_true", help="print JSON instead of text")
    answer = commands.add_parser("answer", help="record your answer in the shared folder")
    answer.add_argument("id", help="the question's id")
    answer.add_argument("number", nargs="?", help="the option's place, from 1")
    answer.add_argument("--other-file", help="a file holding your own words, in place of a number")
    answer.add_argument("--date", help="another day, YYYY-MM-DD")
    results = commands.add_parser("results", help="print the counts for a day, yesterday by default")
    results.add_argument("--date", help="another day, YYYY-MM-DD")
    summary = commands.add_parser("summary", help="print a Markdown summary of a period, the last 14 days by default")
    summary.add_argument("--since", help="the period's first day, YYYY-MM-DD")
    summary.add_argument("--until", help="the period's last day, YYYY-MM-DD, today by default")
    propose = commands.add_parser("propose", help="add a question to the bank, asked on one date only")
    propose.add_argument("--file", required=True, help="a file holding one question, with no Date: line")
    propose.add_argument("--date", required=True, help="the day to ask it, YYYY-MM-DD, after today")
    return parser


COMMANDS = {"check": run_check, "question": run_question, "answer": run_answer, "results": run_results,
            "summary": run_summary, "propose": run_propose}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = build_parser().parse_args(argv)
    try:
        folder = pulse_folder()
        questions, problems = read_bank(folder)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        return COMMANDS[args.command](folder, questions, args)
    except Refused as refusal:
        print(refusal, file=sys.stderr)
    except OSError as error:
        print("pulse: {}".format(error), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
