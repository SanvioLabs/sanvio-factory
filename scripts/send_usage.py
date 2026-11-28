#!/usr/bin/env python3
"""Send your usage bundle to your factory's store, or switch detailed mode (SPEC-004).

    python3 scripts/send_usage.py reports/usage/export.json   # send this file, the one you read
    python3 scripts/send_usage.py --auto                      # a machine nobody watches: yesterday and today, general
    python3 scripts/send_usage.py --heartbeat                 # this machine's loops, alive or not
    python3 scripts/send_usage.py --opt-in detailed           # record your sessions' shell commands, scrubbed
    python3 scripts/send_usage.py --opt-out                   # stop now

Nothing is sent until .sanvio/export.json says "send": true and names a store, and this repo ships neither, so
a copy of the factory never sends anywhere its owner didn't choose. "send": false, or no "send" at all, stops
every send from this machine and leaves the store's settings where they are: the scheduled --auto and
--heartbeat runs then say so and exit 0, and sending a file by hand exits 1. The store is one of:

    {"store": {"kind": "folder", "path": "~/usage-store"}}
    {"store": {"kind": "s3", "bucket": "<bucket>", "prefix": "<team>", "profile": "<cli profile>",
               "region": "<region>", "detailed_key": "<key ARN>"}}

The file names the cloud CLI's profile, never a key: the CLI resolves the credentials. A folder store is a
folder on this machine or a mounted one, for a store you run locally.

What it sends:

- FILE: a bundle python3 scripts/export.py wrote, after checking it against scripts/usage_shape.py, refusing
  any key the shape doesn't name, and running scripts/usage_scrub.py over every command again: if that pass
  would change anything, nothing is sent. The bytes sent are exactly the file's.
- --auto: needs "auto": true in the config. Yesterday's and today's general bundles, each one day, for a
  machine nobody watches. Never detailed mode, whatever it's asked for.
- --heartbeat: one record per loop on this machine (the factory's own, and each project's under .loop/):
  whether its process is alive, whether a loop that isn't was stopped on purpose (stopped, its --for ran out,
  or it never ran; not killed, and not ended on an error), and how many issues wait. For the factory's loop and a project
  export_projects lists, also the issue in progress, its tokens so far and its budget. Another project shows
  under a hashed label with neither, so a heartbeat never names a project you didn't list. No titles ever.

Where it lands: <prefix>/incoming/<node>/<user>/<mode>/<bundle_id>.json for a bundle and
<prefix>/incoming/<node>/heartbeat/<time>.json for a heartbeat, in the bucket or under the folder. The
store's validator moves each to accepted/ or rejected/.

Each bundle sent or refused adds one line to your usage log, export_sent or export_refused, with the mode and
bundle id, never its contents; a heartbeat adds one only when it's refused. A failed send never stops anything:
it says why and exits 1, and the next run tries again.

Only a person turns detailed mode on, for themselves: --opt-in is refused in a headless run, and the guard
asks before an agent runs it for you.
"""
import argparse
import datetime
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))
import export  # noqa: E402 (needs scripts/ on the path first)
import log_chain  # noqa: E402 (same reason)
import names  # noqa: E402 (same reason)
import usage_log  # noqa: E402 (needs .claude/hooks/ on the path first)
import usage_scrub  # noqa: E402 (same reason as export)
import usage_shape  # noqa: E402 (same reason as export)

LAST_SEND = Path("usage") / "last-send"  # under names.state_dir(); the dashboard reads it
ENDED = ("pr", "blocked", "stopped", "skipped")
CLI_TIMEOUT = 60


class Refused(Exception):
    """Nothing was sent, and the message says why."""


class Off(Refused):
    """Sending is off on this machine: a choice, not a failure."""


def safe(part):
    return usage_shape.safe_name(part)


def store_of(cfg):
    """The configured store, checked, or Refused saying how to set one up. Off first, when sending is off."""
    if cfg.get("send") is not True:
        raise Off('sending is off on this machine. "send": true in .sanvio/export.json turns it on')
    store = cfg.get("store")
    if not isinstance(store, dict):
        raise Refused("no store is configured. Add one to .sanvio/export.json, as python3 scripts/send_usage.py "
                      "--help shows; nothing is sent until you do")
    kind = store.get("kind")
    if kind == "folder":
        if not isinstance(store.get("path"), str) or not store["path"].strip():
            raise Refused("the folder store names no path")
    elif kind == "s3":
        for key in ("bucket", "profile"):
            if not isinstance(store.get(key), str) or not store[key].strip():
                raise Refused("the s3 store names no {}".format(key))
    else:
        raise Refused("the store's kind is {!r}; it can be folder or s3".format(kind))
    return store


def where(store):
    """The store, as a person reads it, so a store changed behind their back shows at the next send."""
    if store["kind"] == "folder":
        return "the folder " + store["path"]
    return "s3://{}/{} with the profile {}".format(store["bucket"], (store.get("prefix") or "").strip("/"),
                                                   store["profile"])


def key_for(obj, store):
    """Where an object lands, under the store's prefix."""
    prefix = store.get("prefix") if isinstance(store.get("prefix"), str) else ""
    parts = [safe(p) for p in prefix.strip("/").split("/") if p] + ["incoming", safe(obj["node"])]
    if obj["kind"] == "heartbeat":
        parts += ["heartbeat", safe(obj["ts"].replace(":", "")) + ".json"]
    else:
        parts += [safe(obj["user"]), obj["mode"], safe(obj["bundle_id"]) + ".json"]
    return "/".join(parts)


def check(obj):
    """Refused unless obj is exactly in the shape and every command is already scrubbed."""
    problems = usage_shape.problems(obj)
    if problems:
        raise Refused("it isn't in the v2 shape: " + "; ".join(problems[:5]))
    home = str(Path.home())
    for i, command in enumerate(obj.get("commands") or []):
        again = usage_scrub.scrub(command["text"], home)
        if again != (command["text"], 0):
            raise Refused("command {} would change if scrubbed again, so it may hold a secret or a path that "
                          "must stay here. Nothing was sent".format(i))


def deliver(raw, key, store, detailed=False):
    """Put raw bytes at key in the store. Refused when the store won't take them."""
    if store["kind"] == "folder":
        target = Path(os.path.expanduser(store["path"])) / key
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            part.write_bytes(raw)
            os.replace(part, target)
        except OSError as err:
            raise Refused("the store's folder won't take it: {}".format(type(err).__name__))
        return
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        handle.write(raw)
        body = handle.name
    try:
        argv = ["aws", "s3api", "put-object", "--bucket", store["bucket"], "--key", key, "--body", body,
                "--content-type", "application/json", "--profile", store["profile"]]
        if isinstance(store.get("region"), str) and store["region"]:
            argv += ["--region", store["region"]]
        if detailed:
            if not isinstance(store.get("detailed_key"), str) or not store["detailed_key"]:
                raise Refused("a detailed bundle needs the store's detailed_key, the key only the owner can use")
            argv += ["--server-side-encryption", "aws:kms", "--ssekms-key-id", store["detailed_key"]]
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise Refused("the cloud CLI didn't run: {}".format(type(err).__name__))
        if result.returncode != 0:
            # The CLI's own message names the problem (no credentials, no access) and never a secret's value.
            raise Refused("the store refused it: " + (result.stderr.strip().splitlines() or ["no reason given"])[-1][:200])
    finally:
        os.unlink(body)


def log(root, event, mode, bundle_id):
    if names.logging_off():
        return
    log_chain.append(usage_log.log_path(root), {"ts": usage_log.stamp_of(), "event": event, "mode": mode,
                                                "bundle_id": bundle_id})


def note_sent(root, mode):
    path = names.state_dir(root) / LAST_SEND
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": datetime.date.today().isoformat(), "mode": mode}) + "\n", encoding="utf-8")


def send_bundle(root, raw, store):
    """Check and send one bundle's exact bytes, logging the result. Returns its key."""
    try:
        obj = json.loads(raw)
    except (ValueError, RecursionError):
        raise Refused("it isn't JSON")
    if not isinstance(obj, dict):
        log(root, "export_refused", "unknown", "")
        raise Refused("it isn't a bundle")
    mode = obj.get("mode") if obj.get("mode") in ("general", "detailed") else "unknown"
    bundle_id = str(obj.get("bundle_id", ""))[:64]
    try:
        if obj.get("kind") != "bundle":
            raise Refused("it isn't a bundle")
        check(obj)
        key = key_for(obj, store)
        deliver(raw, key, store, detailed=obj["mode"] == "detailed")
    except Refused:
        log(root, "export_refused", mode, bundle_id)
        raise
    log(root, "export_sent", mode, bundle_id)
    note_sent(root, mode)
    return key


def send_file(root, path):
    store = store_of(export.config(root))
    try:
        raw = Path(path).read_bytes()
    except OSError as err:
        raise Refused("{} can't be read: {}".format(path, type(err).__name__))
    return [send_bundle(root, raw, store)]


def send_auto(root, today=None):
    cfg = export.config(root)
    store = store_of(cfg)
    if cfg.get("auto") is not True:
        raise Refused('--auto needs "auto": true in .sanvio/export.json, for a machine nobody watches')
    today = today or export.utc_today()
    keys = []
    for day in (today - datetime.timedelta(days=1), today):
        found = export.bundle(root, day.isoformat(), today.isoformat(), "general", last=day.isoformat())
        keys.append(send_bundle(root, (json.dumps(found, indent=2) + "\n").encode("utf-8"), store))
    return keys


def label_salt(root):
    """This machine's own random salt for unlisted projects' labels, made once. A plain hash of a folder's
    name could be matched by hashing guesses at it, a customer's name say; a salted one can't."""
    path = names.state_dir(root) / "usage" / "label-salt"
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        salt = secrets.token_bytes(16)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(salt.hex() + "\n", encoding="utf-8")
        return salt


def lock_alive(folder):
    import loop  # here, not at the top: only a heartbeat needs it, and it's the biggest import
    try:
        pid = int((folder / "lock").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return loop.pid_alive(pid)


def on_purpose(folder, status, alive):
    """True when a loop isn't running because someone stopped it, its --for ran out, it finished, or it never
    ran: its run left no lock behind and didn't record an error. A loop killed without a chance to clean up
    leaves its lock, and one that ended on an ERROR or an exception says error, so neither counts."""
    if alive or (folder / "lock").exists():
        return False
    return status.get("ended") != "error"


def beat(folder, label, budget, detail):
    """One loop's heartbeat record. Without detail, only whether it's alive and how many issues wait."""
    try:
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = {}
    status = status if isinstance(status, dict) else {}
    queue = status.get("queue") if isinstance(status.get("queue"), list) else []
    rows = status.get("issues") if isinstance(status.get("issues"), list) else []
    alive = lock_alive(folder)
    issue = tokens = None
    if detail and alive:
        row = next((r for r in rows if isinstance(r, dict) and r.get("state") not in ENDED), None)
        if row is not None:
            issue = export.whole(row.get("number"))
            tokens = export.whole(row.get("tokens"))
    return {"label": label, "alive": alive, "on_purpose": on_purpose(folder, status, alive), "waiting": len(queue),
            "issue": issue, "tokens": tokens, "budget": (budget or None) if detail else None}


def heartbeat(root, now=None):
    """This machine's heartbeat, in the shape. Every loop under .loop/, listed projects by label."""
    cfg = export.config(root)
    listed = export.listed_projects(cfg)
    settings = export.loop_config(root, listed)
    state = Path(root) / ".loop"
    loops = []
    if state.is_dir():
        loops.append(beat(state, export.FACTORY_LABEL, settings[export.FACTORY_LABEL]["max_issue_tokens"], True))
    projects = state / "projects"
    for folder in sorted(p for p in projects.iterdir() if p.is_dir()) if projects.is_dir() else []:
        if folder.name in listed:
            label = listed[folder.name]
            loops.append(beat(folder, label, settings[label]["max_issue_tokens"], True))
        else:
            label = "project-" + hmac.new(label_salt(root), folder.name.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
            loops.append(beat(folder, label, None, False))
    return {"v": usage_shape.V, "kind": "heartbeat", "node": export.node_name(cfg),
            "ts": usage_log.stamp_of(now), "loops": loops,
            "factory": {"commit": export.head_commit(root), "changelog": export.changelog_day(root)}}


def send_heartbeat(root):
    store = store_of(export.config(root))
    obj = heartbeat(root)
    try:
        check(obj)
        key = key_for(obj, store)
        deliver((json.dumps(obj) + "\n").encode("utf-8"), key, store)
    except Refused:
        log(root, "export_refused", "heartbeat", "")
        raise
    return [key]


def main(argv=None, root=ROOT):
    # No abbreviations: --opt-i would otherwise turn detailed mode on past the guard's --opt-in check.
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("file", nargs="?", help="a bundle python3 scripts/export.py wrote, to send as it is")
    which.add_argument("--auto", action="store_true", help="send yesterday's and today's general bundles")
    which.add_argument("--heartbeat", action="store_true", help="send this machine's loops, alive or not")
    which.add_argument("--opt-in", choices=("detailed",), help="turn detailed mode on for yourself")
    which.add_argument("--opt-out", action="store_true", help="turn detailed mode off now")
    args = parser.parse_args(argv)
    if args.opt_out:
        was_on = usage_log.opt_out(root)
        print("Detailed mode is off." if was_on else "Detailed mode wasn't on.")
        return 0
    if args.opt_in:
        try:
            until = usage_log.opt_in(root)
        except PermissionError as err:
            print("Not turned on: {}.".format(err), file=sys.stderr)
            return 1
        print("Detailed mode is on until {}. Your sessions' shell commands are recorded, scrubbed, in {}. "
              "python3 scripts/send_usage.py --opt-out turns it off.".format(until, usage_log.commands_path(root)))
        return 0
    try:
        if args.heartbeat:
            keys = send_heartbeat(root)
        elif args.auto:
            keys = send_auto(root)
        else:
            keys = send_file(root, args.file)
    except Off as err:
        # A scheduled run on a machine that's switched off has done what it was asked: say so, and don't fail.
        print("Not sent: {}.".format(str(err).rstrip(".")), file=sys.stdout if args.auto or args.heartbeat else sys.stderr)
        return 0 if args.auto or args.heartbeat else 1
    except (Refused, ValueError) as err:
        print("Not sent: {}.".format(str(err).rstrip(".")), file=sys.stderr)
        return 1
    for key in keys:
        print("Sent: " + key)
    if keys:
        print("To: " + where(store_of(export.config(root))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
