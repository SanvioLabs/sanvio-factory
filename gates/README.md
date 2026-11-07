# Gates

A gate is a script that exits non-zero when work isn't ready. It checks what's
cheap to check and expensive to miss: an empty section, a placeholder left in,
a number that doesn't match its source.

Your gates go here, one per job: `gates/<job>_gate.py`. The pattern to copy is
[`examples/proposal/gates/proposal_gate.py`](../examples/proposal/gates/proposal_gate.py):

- Standard library only, so it runs anywhere Python 3.9 does
- One `PASS` or `FAIL` line per file, and each problem named on its own line
- Exit 1 when anything fails, so the hook and CI can block on it
- With file paths, check those. With none, check every output the job has,
  which is how CI runs it
- A test in [`tests/`](../tests/) for each thing it checks

Then add a block to [`.githooks/pre-commit`](../.githooks/pre-commit) that runs it on the staged files it
covers, after the ones already there, and a step to [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

Whether a check earns a gate, which of those places it runs in, and what to
check between phases: [`steering/gates.md`](../steering/gates.md).

An API project's security check is the one gate the harness ships ready-made:
`python3 tools/api-security/apply.py --level enforced --runtime lambda-httpapi <repo>`
copies it in with its workflows, and adds it to the repo's `.gates.yaml` if it has
one (otherwise it prints the command for your own gate to run). [`steering/api-security.md`](../steering/api-security.md) has
what it checks.

Never edit a gate to make work pass. Fix the work.
