# api-security

Deny-by-default API routes for a project, at one of four levels. The rules,
the levels and what each one enforces are in the harness's
`api-security.md` steering file; this folder is the tool that installs them.

| Path | What it is |
|---|---|
| `apply.py` | Installs or upgrades a project's copy at a level. `--stamp` rewrites `VERSION` after a change here |
| `api_security_levels.py` | The levels, the files each level installs, and the version hash. The health and setup checks read it; projects never get a copy |
| `python/api_security/` | The library a project copies to `security/api_security/`: route declarations, the check, the approval verifier, the Terraform and dispatch adapters |
| `workflows/` | `security-check.yml` and `security-approval.yml`, copied to `.github/workflows/` |
| `semgrep/` | The rule that flags identity read from a request body, and its tests |
| `rules/` | Per-framework rules copied to a project's `.claude/rules/` |
| `templates/` | `config.json` and the other files a project fills in |
| `tests/` | This tool's suite |

## Run it

```bash
# install or raise a project's level (off, guided, enforced, hardened)
python3 apply.py --level enforced --runtime lambda-httpapi <repo>

# after changing the library, a workflow or the Semgrep rule here
python3 apply.py --stamp
```

`apply.py` reads the project's `security/config.json` before it writes
anything and stops on one it cannot read. Upgrading is the same command at the
project's current level: it replaces what a project copies verbatim and keeps
what the project filled in. Lowering a level needs `--lower`. Pass
`--identity <path>` when the project's `.studio-project.yaml` is not at the
repo root, and `--lang` to override the detected languages.

## Test it

```bash
python3 -m unittest discover -s tests
cd semgrep && semgrep --test --metrics=off .
```
