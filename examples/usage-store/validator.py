#!/usr/bin/env python3
"""The usage store's validator (SPEC-004 REQ-013, REQ-016, REQ-021): one file, two ways to run it.

    python3 examples/usage-store/validator.py --folder ~/usage-store   # sort a local store's incoming/
    # and in the cloud, as the function the bucket calls for each object under incoming/: handler()

Each object under incoming/ is read, checked against scripts/usage_shape.py, the same file the sender
checks against, and moved to accepted/ with the same path, or to rejected/ with a .reason.json beside it.
Nothing stays in incoming/. A bundle whose path doesn't match its own node, user and mode is rejected, so
one sender can't file a bundle as another.

Chain marks: when a bundle replaces an earlier export of the same period (the same bundle_id) with the same
chain_head but different counts, the log changed without a new line being written, and when a bundle has no
chain_head after the person's latest one had one, the log was removed. Either way both bundles get a note
under marks/, as the local review does for a broken chain. A mark shows a change; it doesn't stop one.
Bundles for different periods aren't compared on counts: they'd differ anyway.

A folder store also drops files older than 90 days (SANVIO_KEEP_DAYS) from accepted/, rejected/ and marks/
each time --folder runs: the same 90 days the bucket's lifecycle keeps in the cloud (SPEC-004 PRIV-004).

The first run also writes the _shape/ files the store's views read, so a query over an empty store returns
no rows rather than an error. They hold no numbers and every view leaves them out.

Standard library only, plus boto3 in the cloud function, which the runtime provides.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _folder in (HERE, HERE.parent.parent / "scripts"):  # beside it in the function, scripts/ in a clone
    if (_folder / "usage_shape.py").is_file() and str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))
import usage_shape  # noqa: E402 (needs its folder on the path first)

MAX_BYTES = 4 * 1024 * 1024  # a bundle is a few kilobytes; anything near this is rejected unread

SHAPE_FILES = {
    "accepted/_shape/_shape/general/shape.json": {"kind": "shape"},
    "accepted/_shape/_shape/detailed/shape.json": {"kind": "shape"},
    "accepted/_shape/heartbeat/shape.json": {"kind": "shape"},
}


class Store:
    """What the validator needs of a store: list, read, write and delete keys under a root."""

    def keys(self, prefix):
        raise NotImplementedError  # each store below lists its own way

    def read(self, key):
        raise NotImplementedError  # each store below reads its own way

    def write(self, key, raw, like=None):
        raise NotImplementedError  # each store below writes its own way

    def delete(self, key):
        raise NotImplementedError  # each store below deletes its own way

    def size(self, key):
        raise NotImplementedError  # each store below sizes its own way


class FolderStore(Store):
    def __init__(self, root):
        self.root = Path(os.path.expanduser(str(root)))

    def keys(self, prefix):
        base = self.root / prefix
        if base.is_file():
            return [prefix]
        if not base.is_dir():
            return []
        return sorted(str(p.relative_to(self.root)).replace(os.sep, "/") for p in base.rglob("*.json")
                      if not p.name.endswith(".part"))

    def read(self, key):
        return (self.root / key).read_bytes()

    def write(self, key, raw, like=None):
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        part.write_bytes(raw)
        os.replace(part, target)

    def delete(self, key):
        (self.root / key).unlink()

    def size(self, key):
        return (self.root / key).stat().st_size

    def prune(self, days, now=None):
        """Remove files under accepted/, rejected/ and marks/ last changed over `days` ago. Returns their keys."""
        cutoff = (time.time() if now is None else now) - days * 86400
        gone = []
        for top in ("accepted", "rejected", "marks"):
            base = self.root / top
            if not base.is_dir():
                continue
            for path in base.rglob("*.json"):
                key = str(path.relative_to(self.root)).replace(os.sep, "/")
                if key not in SHAPE_FILES and path.stat().st_mtime < cutoff:
                    path.unlink()
                    gone.append(key)
        return sorted(gone)


def keep_days():
    """The 90 days the local logs keep, or SANVIO_KEEP_DAYS, as for them."""
    try:
        return max(1, int(os.environ.get("SANVIO_KEEP_DAYS", "90")))
    except ValueError:
        return 90


class BucketStore(Store):
    """A bucket, through boto3, under a prefix. A detailed object keeps its encryption key when it moves."""

    def __init__(self, bucket, prefix, client=None):
        import boto3  # the function's runtime has it; a folder store never imports it
        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.client = client or boto3.client("s3")

    def full(self, key):
        return self.prefix + "/" + key if self.prefix else key

    def keys(self, prefix):
        out, token = [], None
        cut = len(self.prefix) + 1 if self.prefix else 0
        while True:
            args = {"Bucket": self.bucket, "Prefix": self.full(prefix)}
            if token:
                args["ContinuationToken"] = token
            page = self.client.list_objects_v2(**args)
            out += [item["Key"][cut:] for item in page.get("Contents", []) if item["Key"].endswith(".json")]
            token = page.get("NextContinuationToken")
            if not token:
                return sorted(out)

    def read(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=self.full(key))["Body"].read()

    def write(self, key, raw, like=None):
        args = {"Bucket": self.bucket, "Key": self.full(key), "Body": raw, "ContentType": "application/json"}
        if like and like.get("ServerSideEncryption") == "aws:kms":
            args.update(ServerSideEncryption="aws:kms", SSEKMSKeyId=like["SSEKMSKeyId"])
        self.client.put_object(**args)

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=self.full(key))

    def size(self, key):
        return self.client.head_object(Bucket=self.bucket, Key=self.full(key))["ContentLength"]

    def encryption(self, key):
        head = self.client.head_object(Bucket=self.bucket, Key=self.full(key))
        return {k: head[k] for k in ("ServerSideEncryption", "SSEKMSKeyId") if k in head}


def expected_tail(obj):
    """The path an object's own fields say it belongs at, after incoming/: what the sender's key_for() writes."""
    if obj.get("kind") == "heartbeat":
        return "{}/heartbeat/".format(obj.get("node"))
    return "{}/{}/{}/{}.json".format(obj.get("node"), obj.get("user"), obj.get("mode"), obj.get("bundle_id"))


def why_rejected(tail, raw):
    """None when the object at incoming/<tail> may be accepted, else the reason."""
    try:
        obj = json.loads(raw)
    except (ValueError, RecursionError):
        return "not JSON, or nested too deep"
    problems = usage_shape.problems(obj)
    if problems:
        return "; ".join(problems[:10])
    want = expected_tail(obj)
    if not (tail.startswith(want) if obj["kind"] == "heartbeat" else tail == want):
        return "its path doesn't match its own node, user, mode or id"
    return None


def same_person(store, obj):
    """This person's other accepted bundles, newest first, as objects."""
    found = []
    for key in store.keys("accepted/{}/{}/".format(obj["node"], obj["user"])):
        try:
            other = json.loads(store.read(key))
        except (ValueError, OSError):
            continue
        if other.get("kind") == "bundle" and other.get("bundle_id") != obj["bundle_id"]:
            found.append(other)
    return sorted(found, key=lambda o: o.get("exported", ""), reverse=True)


def chain_marks(store, obj, dest):
    """The marks a newly accepted bundle earns: against the export of the same period it replaces at `dest`,
    and against the same person's latest other bundle."""
    if obj.get("kind") != "bundle":
        return []
    if dest in store.keys(dest):
        try:
            before = json.loads(store.read(dest))
        except (ValueError, OSError):
            before = {}
        if (obj.get("chain_head") and obj["chain_head"] == before.get("chain_head")
                and obj.get("usage") != before.get("usage")):
            return [(o, "the usage log changed without a new line: same chain_head, different counts")
                    for o in (obj, before)]
    earlier = [o for o in same_person(store, obj) if o.get("exported", "") <= obj.get("exported", "")]
    if earlier and earlier[0].get("chain_head") and not obj.get("chain_head"):
        return [(o, "the usage log was removed: no chain_head after one that had one") for o in (obj, earlier[0])]
    return []


def sort_one(store, key):
    """Move one incoming/ object to accepted/ or rejected/. Returns (where it went, reason or None)."""
    tail = key[len("incoming/"):]
    if store.size(key) > MAX_BYTES:
        raw, reason = b"{}", "larger than {} bytes, not read".format(MAX_BYTES)
    else:
        raw = store.read(key)
        reason = why_rejected(tail, raw)
    # Only a detailed bundle keeps its key: a general one under it would be unreadable to the team's Grafana.
    like = store.encryption(key) if isinstance(store, BucketStore) and "/detailed/" in key else None
    if reason:
        dest = "rejected/" + tail
        store.write(dest, raw, like)
        store.write(dest[:-len(".json")] + ".reason.json", (json.dumps({"reason": reason}) + "\n").encode("utf-8"))
    else:
        dest = "accepted/" + tail
        obj = json.loads(raw)
        for n, (marked, why) in enumerate(chain_marks(store, obj, dest)):
            note = {"bundle_id": marked["bundle_id"], "node": marked["node"], "user": marked["user"],
                    "exported": marked.get("exported"), "reason": why}
            # the same id can be both bundles, the new export and the one it replaces, so each gets its own file
            name = marked["bundle_id"] + ("" if n == 0 else ".before")
            store.write("marks/{}/{}/{}.json".format(marked["node"], marked["user"], name),
                        (json.dumps(note) + "\n").encode("utf-8"))
        store.write(dest, raw, like)
    store.delete(key)
    return dest, reason


def ensure_shape(store):
    have = set(store.keys("accepted/_shape/"))
    for key, body in SHAPE_FILES.items():
        if key not in have:
            store.write(key, (json.dumps(body) + "\n").encode("utf-8"))


def sort_all(store):
    ensure_shape(store)
    return [sort_one(store, key) for key in store.keys("incoming/")]


def handler(event, context):
    """The cloud function: one call per object the bucket says arrived under <prefix>/incoming/."""
    from urllib.parse import unquote_plus
    prefix = os.environ.get("USAGE_PREFIX", "")
    out = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        full = unquote_plus(record["s3"]["object"]["key"])
        store = BucketStore(bucket, prefix)
        key = full[len(store.prefix) + 1:] if store.prefix else full
        if key.startswith("incoming/"):
            ensure_shape(store)
            out.append(sort_one(store, key))
    return {"sorted": len(out), "rejected": sum(1 for _, reason in out if reason)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", required=True, help="the local store's folder, as .sanvio/export.json names it")
    args = parser.parse_args(argv)
    store = FolderStore(args.folder)
    results = sort_all(store)
    for dest, reason in results:
        print("{}{}".format(dest, "  ({})".format(reason) if reason else ""))
    gone = store.prune(keep_days())
    print("{} sorted, {} rejected, {} older than {} days removed.".format(
        len(results), sum(1 for _, r in results if r), len(gone), keep_days()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
