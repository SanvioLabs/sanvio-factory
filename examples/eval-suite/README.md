# A tiny eval suite

The smallest suite [`scripts/eval_harness.py`](../../scripts/eval_harness.py) can run, to show the format. Copy its shape for your own. It's public so you can read it, which means an agent could too, so it can't tell you how good a harness is. A real suite's folder belongs in a private repo, outside the harness, and somewhere its agents aren't allowed to read.

```
suite.json        name, seed, key, issues in order, required_checks
seed/             the repo a run starts from, with its CI workflow. Made-up data only
issues/           one Markdown file per issue, its first line the title
key/
  score           prints {"tests": [{"name", "passed"}], "traps": [{"name", "avoided"}]}
  reference/      files that overlay the seed to make the right answer
  wrong/<name>/   files that overlay the seed to make a known wrong answer
```

`required_checks` names the seed's CI jobs, and [`key/score`](key/score) gets `RUN_DIR`, `BASE_SHA`, `PR_NUMBERS` and `RUN_REPO`. `"public_example": true` is what lets this suite's key sit inside the harness. Don't set it on a real suite.

Check a suite before you use it. This spends no tokens and creates no repo, and it passes only when the seed fails, each wrong answer fails and the reference passes:

    python3 scripts/eval_harness.py validate examples/eval-suite

Run a suite through this harness's loop. The seed needs a `loop.json` with its `test_command`, as this one has. A run creates a private repo in the owner you name and spends model tokens:

    python3 scripts/eval_harness.py run <suite> --owner <your-org> --merge-in-run-repo --start \
      'gh label create loop-ready -R {repo} --force && gh issue edit {issue} -R {repo} --add-label loop-ready && for i in $(seq 40); do gh issue list -R {repo} --label loop-ready --json number -q ".[].number" | grep -qx {issue} && break; sleep 3; done && python3 scripts/loop.py run --once --issue {issue} --project {project}'

The wait in the middle matters: a new label can take a few seconds to show in GitHub's issue list, and a loop that looks too soon finds nothing ready.

To spend no model tokens, point the loop at a local Ollama model. Use a copy of this harness whose root `loop.json` names a wrapper called `claude`, which sets `ANTHROPIC_BASE_URL=http://127.0.0.1:11434` before it runs the real one. Pass `--harness <copy>` and `--usage-command 'echo 0'`, because Claude Code prices local tokens as though they were Anthropic's. Compare such runs only with runs on the same models.

Then compare two runs, by the names `list` prints:

    python3 scripts/eval_harness.py compare <run-a> <run-b>

Scoring runs code an agent wrote, as CI would. Keep made-up data in every suite.
