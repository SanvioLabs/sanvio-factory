#!/usr/bin/env python3
"""Check a workflow folder against docs/building-workflows.md.

    python3 scripts/check_workflow.py workflows/<name>

Checks the parts *The workflow folder* lists, the manifest *The manifest*
describes, and everything *The trust tests* asks: it runs the workflow's gate
on every eval case, every sample output and the template, and runs the
workflow's own tests. Prints PASS and exits 0, or prints each problem on its own
line and exits 1.

Every command runs from the workflow's folder, with this Python, a 120-second
limit and no bytecode written, so the folder is left exactly as it was. The gate
runs as a subprocess and is never imported. Standard library only, Python 3.9+.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TIMEOUT = 120
KEYS = ["name", "description", "owner", "status", "runs", "trigger", "inputs", "output", "standard",
        "skill", "gate", "reviewer", "template", "approves", "receives", "never", "restricted_data",
        "blueprint"]
PATH_KEYS = ["inputs", "output", "standard", "skill", "gate", "reviewer", "template", "blueprint"]
STATUSES = ("draft", "live", "retired")
RUNS = ("chat", "loop", "schedule")
MIN_GATE_CASES = 6
MIN_REVIEW_CASES = 2
# standard/ on its own, never the tail of sample/standard/ or of a longer word.
OWN_STANDARD = re.compile(r"(?<![\w/])standard/")
RAN = re.compile(r"^Ran (\d+) tests?\b", re.M)
FAILED_TEST = re.compile(r"^(?:FAIL|ERROR): .+$", re.M)


def run(folder, args):
    """(exit code, stdout and stderr together) for a Python command run from the folder."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        done = subprocess.run([sys.executable] + args, cwd=str(folder), env=env, capture_output=True,
                              text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, "timed out after {} seconds".format(TIMEOUT)
    return done.returncode, done.stdout + done.stderr


def first_line(output):
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[0] if lines else "(it printed nothing)"


def cases(folder, kind):
    """The case folders under evals/<kind>/, sorted."""
    where = folder / "evals" / kind
    return sorted(p for p in where.iterdir() if p.is_dir()) if where.is_dir() else []


def rel(folder, path):
    return path.relative_to(folder).as_posix()


def check_paths(folder, name):
    """Every part of *The workflow folder* that isn't there."""
    found = []
    for path in ("workflow.json", "README.md", "agents/reviewer.md", "inbox/.gitkeep", "out/.gitkeep",
                 "tests/test_{}_gate.py".format(name.replace("-", "_"))):
        if not (folder / path).is_file():
            found.append("missing: " + path)
    for path in ("standard/", "evals/gate/", "evals/review/", "sample/inputs/", "sample/outputs/",
                 "sample/standard/"):
        if not (folder / path).is_dir():
            found.append("missing: " + path)
    for pattern, what in (("templates/*.md", "a template"), ("skills/*/SKILL.md", "a skill"),
                          ("gates/*_gate.py", "a gate")):
        if not any(p.is_file() for p in folder.glob(pattern)):
            found.append("missing: {} ({})".format(pattern, what))
    for kind in ("gate", "review"):
        for case in cases(folder, kind):
            for part in ("case.json", "output.md"):
                if not (case / part).is_file():
                    found.append("missing: {}/{}".format(rel(folder, case), part))
    return found


def read_manifest(folder):
    """(the manifest, or None if it can't be used, and its problems)."""
    path = folder / "workflow.json"
    if not path.is_file():
        return None, []  # check_paths names it
    try:
        manifest = json.loads(path.read_text())
    except (ValueError, UnicodeDecodeError) as error:
        return None, ["workflow.json: not valid JSON ({})".format(error)]
    if not isinstance(manifest, dict):
        return None, ["workflow.json: not a JSON object"]
    return manifest, check_manifest(folder, manifest)


def check_manifest(folder, manifest):
    found = []
    for key in KEYS:
        if key not in manifest:
            found.append('workflow.json: no "{}" key'.format(key))
    for key in KEYS:
        if key in manifest and key not in ("runs", "never") and not isinstance(manifest[key], str):
            found.append('workflow.json: "{}" is not a string'.format(key))
    if isinstance(manifest.get("name"), str) and manifest["name"] != folder.name:
        found.append('workflow.json: name "{}" is not the folder\'s name "{}"'.format(manifest["name"], folder.name))
    if "status" in manifest and manifest["status"] not in STATUSES:
        found.append('workflow.json: status "{}" is not one of {}'.format(manifest["status"], ", ".join(STATUSES)))
    runs = manifest.get("runs")
    if "runs" in manifest:
        if not isinstance(runs, list) or not runs:
            found.append("workflow.json: runs is not a list of {}".format(", ".join(RUNS)))
        else:
            for value in runs:
                if value not in RUNS:
                    found.append('workflow.json: runs holds "{}", not one of {}'.format(value, ", ".join(RUNS)))
            restricted = manifest.get("restricted_data")
            if "schedule" in runs and restricted != "none":
                found.append('workflow.json: runs lists schedule while restricted_data is "{}", not "none"'
                             .format(restricted))
    if "never" in manifest and not isinstance(manifest["never"], list):
        found.append("workflow.json: never is not a list")
    for key in PATH_KEYS:
        value = manifest.get(key)
        if isinstance(value, str) and value and not (folder / value).exists():
            found.append('workflow.json: {} "{}" does not exist'.format(key, value))
        elif isinstance(value, str) and not value:
            found.append("workflow.json: {} is empty".format(key))
    return found


def usable(folder, manifest, key):
    """The manifest's path for `key` when it names a file that's there, else None."""
    value = (manifest or {}).get(key)
    if isinstance(value, str) and value and (folder / value).is_file():
        return value
    return None


def check_gate(folder, gate, template):
    """The trust tests that run the gate."""
    found = []
    gate_cases = cases(folder, "gate")
    review_cases = cases(folder, "review")
    if len(gate_cases) < MIN_GATE_CASES:
        found.append("evals/gate: {} case{}, and it needs at least {}".format(
            len(gate_cases), "" if len(gate_cases) == 1 else "s", MIN_GATE_CASES))
    if len(review_cases) < MIN_REVIEW_CASES:
        found.append("evals/review: {} case{}, and it needs at least {}".format(
            len(review_cases), "" if len(review_cases) == 1 else "s", MIN_REVIEW_CASES))
    for case in gate_cases:
        found += check_gate_case(folder, gate, case)
    for case in review_cases:
        if not (case / "output.md").is_file():
            continue  # check_paths names it
        code, output = run(folder, [gate, rel(folder, case / "output.md")])
        if code != 0:
            found.append("{}: the gate fails it, so it sits in the wrong folder: a case the gate refuses "
                         "belongs in evals/gate/ ({})".format(rel(folder, case), first_line(output)))
    outputs = sorted(p for p in (folder / "sample" / "outputs").glob("*") if p.is_file()
                     and not p.name.startswith("."))
    if (folder / "sample" / "outputs").is_dir() and not outputs:
        found.append("sample/outputs/: no sample outputs, so nothing shows the gate passing")
    for output_file in outputs:
        code, output = run(folder, [gate, rel(folder, output_file)])
        if code != 0:
            found.append("{}: fails the gate: {}".format(rel(folder, output_file), first_line(output)))
    if template:
        code, output = run(folder, [gate, template])
        if code == 0:
            found.append("{}: passes the gate unfilled, so the gate can't tell a draft from template text"
                         .format(template))
    return found


def check_gate_case(folder, gate, case):
    name = rel(folder, case)
    if not (case / "case.json").is_file() or not (case / "output.md").is_file():
        return []  # check_paths names it
    try:
        spec = json.loads((case / "case.json").read_text())
    except (ValueError, UnicodeDecodeError) as error:
        return ["{}: case.json is not valid JSON ({})".format(name, error)]
    if not isinstance(spec, dict):
        return ["{}: case.json is not a JSON object".format(name)]
    found = []
    if spec.get("expect") != "fail":
        found.append('{}: expect is "{}", and a gate case expects "fail"'.format(name, spec.get("expect")))
    says = spec.get("says")
    if not isinstance(says, str) or not says:
        found.append("{}: case.json has no says".format(name))
    code, output = run(folder, [gate, rel(folder, case / "output.md")])
    if code is None:
        found.append("{}: the gate {}".format(name, output))
    elif code != 1:
        found.append("{}: the gate exited {}, and it must refuse this case with exit 1".format(name, code))
    elif isinstance(says, str) and says and says not in output:
        found.append('{}: the gate refused it without saying "{}" ({})'.format(name, says, first_line(output)))
    return found


def frontmatter_says_invented(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, sep, value = line.partition(":")
        if sep and key.strip() == "invented" and value.strip() == "true":
            return True
    return False


def check_inputs(folder):
    found = []
    for path in sorted((folder / "sample" / "inputs").glob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        name = rel(folder, path)
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            found.append("{}: no invented: true (it can't be read as text)".format(name))
            continue
        if path.suffix == ".json":
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            ok = isinstance(data, dict) and data.get("invented") is True
            where = "at the top level"
        else:
            ok = frontmatter_says_invented(text)
            where = "in the frontmatter"
        if not ok:
            found.append("{}: no invented: true {}".format(name, where))
    return found


def check_standard_refs(folder):
    """Sample outputs and evals point at sample/standard/, never at standard/."""
    found = []
    files = [p for p in (folder / "sample" / "outputs").glob("*") if p.is_file()]
    for kind in ("gate", "review"):
        for case in cases(folder, kind):
            files += [case / part for part in ("case.json", "output.md") if (case / part).is_file()]
    for path in sorted(files):
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if OWN_STANDARD.search(line):
                found.append("{}: line {} names standard/, and it must name sample/standard/".format(
                    rel(folder, path), number))
    return found


def check_tests(folder):
    if not (folder / "tests").is_dir():
        return []  # check_paths names the test file
    code, output = run(folder, ["-m", "unittest", "discover", "-s", "tests"])
    if code is None:
        return ["tests: the workflow's tests {}".format(output)]
    ran = RAN.findall(output)
    if not ran or int(ran[-1]) == 0:
        return ["tests: the workflow's tests ran no tests"]
    if code != 0:
        failed = FAILED_TEST.findall(output)
        if failed:
            return ["tests: the workflow's tests fail: {}".format(line) for line in failed]
        return ["tests: the workflow's tests fail: {}".format(first_line(output))]
    return []


def check(folder):
    """Every problem with the workflow folder. An empty list means it passes."""
    folder = Path(folder).resolve()
    found = check_paths(folder, folder.name)
    manifest, manifest_problems = read_manifest(folder)
    found += manifest_problems
    gate = usable(folder, manifest, "gate")
    template = usable(folder, manifest, "template")
    if gate:
        found += check_gate(folder, gate, template)
        if not template:
            found.append("skipped: the template check, because workflow.json names no template that exists")
    else:
        found.append("skipped: the gate's evals, sample outputs and template, because workflow.json "
                     "names no gate that exists")
    found += check_inputs(folder)
    found += check_standard_refs(folder)
    found += check_tests(folder)
    return found


def main(argv):
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[1].strip())
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    folder = Path(argv[0])
    if not folder.is_dir():
        print("{}: not a folder".format(argv[0]))
        return 1
    found = check(folder)
    if found:
        for line in found:
            print(line)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
