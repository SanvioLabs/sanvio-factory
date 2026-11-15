#!/usr/bin/env python3
"""What a factory eval run's Claude Code sessions cost, at your prices, for eval_factory.py's --usage-command.

    python3 scripts/eval_session_cost.py {clone}              prints the run's cost in dollars, and nothing else
    python3 scripts/eval_session_cost.py CLONE --detail       tokens and dollars by model, as JSON

A factory that isn't this one reports no cost of its own, so a run's cost reads "not reported". When that
factory runs Claude Code in the run's clone, as most do, this adds up what those sessions used. It reads
Claude Code's own transcripts (CLAUDE_CONFIG_DIR/projects, or ~/.claude/projects, or --projects), and counts
each reply once, from every session whose working folder is the clone or inside it, so worktrees and
subagents count too. Each run's clone is new, so nothing from another run is counted.

Prices come from .sanvio/prices.json, the same file the dashboard uses (copy scripts/prices.example.json,
then put in each model you use, in dollars per million tokens, from your provider's price list), or --prices.
A model is priced by its exact name, or else by the longest name in the file that it starts with, so
"claude-haiku-4-5" prices "claude-haiku-4-5-20251001". The figure is an estimate at those prices, not
what was billed.

It prints nothing on stdout and exits 1 when it can't give the whole cost: no sessions in the clone, no
prices file, or a model with tokens and no price. The run then reads "not reported", never a number that's
too low. Claude Code only: other tools keep their own logs.

From Sanvio Factory by Sanvio Labs, MIT: https://github.com/SanvioLabs/sanvio-factory
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import names  # noqa: E402  beside this file: the state folder

COUNTS = (("input_tokens", "input"), ("output_tokens", "output"),
          ("cache_creation_input_tokens", "cache_writes"), ("cache_read_input_tokens", "cache_reads"))
PER = 1_000_000  # prices.json's figures are dollars per this many tokens
FOLDER_NAME_LIMIT = 200  # Claude Code shortens a longer folder name and adds a hash


class CostError(Exception):
    """Why the whole cost can't be given."""


def projects_dir(given=None):
    if given:
        return Path(given)
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(config) / "projects" if config else Path.home() / ".claude" / "projects"


def folder_prefix(clone):
    """The start of the transcript folder name for sessions in clone, or any folder inside it."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(clone))[:FOLDER_NAME_LIMIT]


def inside(cwd, clone):
    return cwd == str(clone) or cwd.startswith(str(clone).rstrip("/") + "/")


def usage_by_model(clone, projects):
    """{model: [input, output, cache writes, cache reads]} over each reply once, in sessions under clone."""
    clone = Path(clone).resolve()
    prefix, seen, models = folder_prefix(clone), set(), {}
    if not projects.is_dir():
        return models
    for folder in projects.iterdir():
        if not folder.is_dir() or not folder.name.startswith(prefix):
            continue
        for log in folder.rglob("*.jsonl"):
            try:
                lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or not inside(str(entry.get("cwd") or ""), clone):
                    continue
                message = entry.get("message")
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                usage, key = message.get("usage"), message.get("id") or entry.get("requestId")
                if not isinstance(usage, dict) or not key or key in seen:
                    continue
                seen.add(key)
                counts = [usage.get(field) if isinstance(usage.get(field), int) else 0 for field, _ in COUNTS]
                if not any(counts):
                    continue
                total = models.setdefault(str(message.get("model") or "unknown"), [0, 0, 0, 0])
                for index, count in enumerate(counts):
                    total[index] += count
    return models


def load_prices(path):
    """{model name: [dollars per million for each of COUNTS]}. CostError when the file can't be used."""
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CostError("no prices file at {}: copy scripts/prices.example.json there and fill it in".format(path))
    except (OSError, ValueError):
        raise CostError("{} can't be read as JSON".format(path))
    models = found.get("models") if isinstance(found, dict) else None
    if not isinstance(models, dict):
        raise CostError("{} has no models".format(path))
    prices = {}
    for name, entry in models.items():
        rates = [entry.get(field) if isinstance(entry, dict) else None for _, field in COUNTS]
        if all(isinstance(r, (int, float)) and not isinstance(r, bool) and r >= 0 and math.isfinite(r) for r in rates):
            prices[str(name)] = [float(r) for r in rates]
    return prices


def price_for(model, prices):
    if model in prices:
        return prices[model]
    matches = [name for name in prices if model.startswith(name)]
    return prices[max(matches, key=len)] if matches else None


def cost(models, prices):
    """(total dollars, {model: {tokens, dollars}}). CostError when a model with tokens has no price."""
    total, detail, missing = 0.0, {}, []
    for model, counts in sorted(models.items()):
        rates = price_for(model, prices)
        if rates is None:
            missing.append(model)
            continue
        dollars = sum(count * rate for count, rate in zip(counts, rates)) / PER
        total += dollars
        detail[model] = {"tokens": sum(counts), "dollars": round(dollars, 4)}
    if missing:
        raise CostError("no price for {}".format(", ".join(missing)))
    return total, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description="What a run's Claude Code sessions cost, at your prices.")
    parser.add_argument("clone", help="the run's clone: pass {clone} in --usage-command")
    parser.add_argument("--prices", help="the prices file: .sanvio/prices.json by default")
    parser.add_argument("--projects", help="Claude Code's projects folder, if it isn't the usual one")
    parser.add_argument("--detail", action="store_true", help="tokens and dollars by model, as JSON")
    args = parser.parse_args(argv)
    models = usage_by_model(args.clone, projects_dir(args.projects))
    try:
        if not models:
            raise CostError("no Claude Code sessions found in {}".format(args.clone))
        total, detail = cost(models, load_prices(args.prices or names.state_dir(ROOT) / "prices.json"))
    except CostError as err:
        print("Cost not reported: {}".format(err), file=sys.stderr)
        return 1
    if args.detail:
        print(json.dumps({"cost": round(total, 4), "models": detail}, indent=2))
    else:
        print("{:.4f}".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
