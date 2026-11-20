"""Make .github/workflows/review-pr-bedrock.yml from .github/workflows/review-pr.yml (#647).

The Bedrock review is its own workflow, so only a caller that runs on Bedrock grants id-token: write; a caller
with a Claude key calls review-pr.yml and grants nothing new. Everything both share is review-pr.yml's: this
script copies it and makes the Bedrock changes, each at an anchor that must appear exactly once, so an edit to
review-pr.yml that moves an anchor stops the build here rather than leaving a step out.

    python3 scripts/bedrock_workflow.py           writes review-pr-bedrock.yml
    python3 scripts/bedrock_workflow.py --check   exits 1 if the committed file isn't what this makes

Edit review-pr.yml or this script, never review-pr-bedrock.yml. tests/test_review_pr_bedrock.py fails while the
two differ.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".github" / "workflows" / "review-pr.yml"
TARGET = ROOT / ".github" / "workflows" / "review-pr-bedrock.yml"
WORKFLOW_FILE = ".github/workflows/review-pr-bedrock.yml"

HEADER = """\
# GENERATED from review-pr.yml by scripts/bedrock_workflow.py. Edit
# review-pr.yml or the script and run `python3 scripts/bedrock_workflow.py`,
# never this file: tests/test_review_pr_bedrock.py fails while the two differ.
#
# This is review-pr.yml for a product repo that reviews on Amazon Bedrock in
# its own AWS account, with no Claude credential. Its caller grants
# id-token: write, which review-pr.yml's callers never do. Each agent's review
# job trades its GitHub OIDC token for a 15-minute session on the caller's
# role, from examples/ci/bedrock-review-role.yml, and runs Claude with
# CLAUDE_CODE_USE_BEDROCK set and the caller's aws-model pinned.
#
# What holds the role to this workflow, beyond the role's own trust:
#   - Before any other step, the review job reads its own OIDC token's
#     job_workflow_ref and job_workflow_sha, and checks out the harness from
#     that repo at that commit, so the harness code that runs where the token
#     can be minted is the commit the role trusts, never one a caller names.
#     factory-repo has to name the same repo, or the job stops.
#   - Agents run with Read, Grep and Glob only: a ci-shell: line stops the run.
#   - The CLI installs with every package script off but its own installer.
#   - base/ and head/ lose their links before the agent reads them, and the
#     CLI runs without the token-request values.
# What doesn't hold: any step in the review job can ask GitHub for the OIDC
# token and assume the role itself, for as long as the role's
# MaxSessionDuration, not just the action's 15 minutes; the steps after the
# review still could. The checks above are what keep code a caller chose out
# of that job. The agents and grade jobs
# check out factory-repo's default branch as review-pr.yml does, and get no
# id-token: the workflow's permissions below leave it out.
#
# Where the comments below speak of a Claude credential, this workflow has
# none: read the AWS role.
#
"""

EDITS = [
    # Inputs: the role, the region and the model, all required.
    ("""\
      factory-repo:
        description: "This factory repo, as owner/name. A called workflow can't read its own repo's name."
        required: true
        type: string
""", """\
      factory-repo:
        description: "This factory repo, as owner/name. It has to match the repo this workflow runs from, or the review stops."
        required: true
        type: string
      aws-role-arn:
        description: "The ARN of the AWS role the review assumes through OIDC, from examples/ci/bedrock-review-role.yml."
        required: true
        type: string
      aws-region:
        description: "The AWS region the review calls Bedrock in. It has to be one the role's BedrockRegions allows."
        required: true
        type: string
      aws-model:
        description: "The Bedrock model ID or inference profile the review runs, served from regions the role allows."
        required: true
        type: string
"""),
    # No Claude credential on this path.
    ("""\
      ANTHROPIC_API_KEY:
        description: "The Anthropic API key Claude reviews with, scoped to a workspace."
        required: false
      CLAUDE_CODE_OAUTH_TOKEN:
        description: "Instead of the API key: a Claude subscription token from claude setup-token."
        required: false
""", ""),
    # The key check becomes Dependabot's: its pull requests get no Actions secrets, so no deploy key.
    ("""\
      - name: Skip when Claude has no key
        if: steps.scope.outputs.review == 'true' && env.REVIEW_SKIPPED != 'true'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: |
          if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
            echo "REVIEW_SKIPPED=true" >> "$GITHUB_ENV"
            echo "::notice::This pull request has no ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN (Dependabot's don't get Actions secrets), so the review skips."
          fi
""", """\
      - name: Skip a Dependabot pull request
        if: steps.scope.outputs.review == 'true' && env.REVIEW_SKIPPED != 'true'
        env:
          FACTORY_DEPLOY_KEY: ${{ secrets.FACTORY_DEPLOY_KEY }}
          ACTOR: ${{ github.actor }}
        run: |
          if [ -z "$FACTORY_DEPLOY_KEY" ] && [ "$ACTOR" = "dependabot[bot]" ]; then
            echo "REVIEW_SKIPPED=true" >> "$GITHUB_ENV"
            echo "::notice::Dependabot's pull requests get no Actions secrets, so there's no deploy key and the review skips."
          fi
"""),
    # Agents run with Read, Grep and Glob only.
    ("""\
              tools = ["Read", "Grep", "Glob"] + ["Bash({}:*)".format(command) for command in shell(path)]
""", """\
              if shell(path):
                  fail("{} has a ci-shell: line. The Bedrock review runs agents with Read, Grep and Glob only, "
                       "since the AWS session is in the review's environment.".format(path))
              tools = ["Read", "Grep", "Glob"]
"""),
    # The review job alone asks for id-token, and checks its own identity before anything else runs.
    ("""\
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        agent: ${{ fromJSON(needs.agents.outputs.matrix) }}
    steps:
      # The default branch, not a pinned ref: one copy of the rules, followed
      # by every repo that calls this.
      - name: Check out the harness
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: ${{ inputs.factory-repo }}
          ssh-key: ${{ secrets.FACTORY_DEPLOY_KEY }}
""", """\
    timeout-minutes: 30
    # The workflow's two, and id-token: write for the OIDC token, on this job
    # alone: the agents and grade jobs run code from factory-repo's default
    # branch and never get it.
    permissions:
      contents: read
      pull-requests: write
      id-token: write
    strategy:
      fail-fast: false
      matrix:
        agent: ${{ fromJSON(needs.agents.outputs.matrix) }}
    steps:
      # First, before any code from a checkout can run: the job's own OIDC
      # token names the workflow file and the commit GitHub is running, the
      # same job_workflow_ref the role trusts. The harness is checked out from
      # that repo at that commit, so the caller's factory-repo and its deploy
      # key choose nothing that runs here. The token is read from the runner's
      # own endpoint and never printed.
      - name: Check this is the factory's own workflow
        id: own
        env:
          FACTORY_REPO: ${{ inputs.factory-repo }}
        run: |
          python3 - <<'EOF'
          import base64
          import json
          import os
          import re
          import sys
          import urllib.request

          WORKFLOW = "/""" + WORKFLOW_FILE + """@"
          REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


          def fail(message):
              print("::error::" + message)
              sys.exit(1)


          url, bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
          if not url or not bearer:
              fail("This job has no OIDC token. The caller has to grant id-token: write to the review job.")
          request = urllib.request.Request(url + "&audience=sts.amazonaws.com",
                                           headers={"Authorization": "bearer " + bearer})
          try:
              with urllib.request.urlopen(request, timeout=30) as response:
                  token = json.load(response)["value"]
              body = token.split(".")[1]
              claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
          except Exception as err:  # any failure reading the token stops the job
              fail("Couldn't read this job's OIDC token: {}".format(type(err).__name__))
          ref, sha = str(claims.get("job_workflow_ref", "")), str(claims.get("job_workflow_sha", ""))
          repo, found, _ = ref.partition(WORKFLOW)
          if not found or not REPO.fullmatch(repo) or not re.fullmatch(r"[0-9a-f]{40}", sha):
              fail("This job's OIDC token doesn't name {} and a commit, so it isn't the factory's own "
                   "workflow: {!r}".format(WORKFLOW.strip("/@"), ref))
          if repo.lower() != os.environ.get("FACTORY_REPO", "").lower():
              fail("factory-repo is {!r}, but this workflow runs from {}. They have to be the same repo.".format(
                  os.environ.get("FACTORY_REPO", ""), repo))
          with open(os.environ["GITHUB_OUTPUT"], "a") as out:
              out.write("repo={}\\nsha={}\\n".format(repo, sha))
          print("This workflow: {} at {}".format(repo, sha))
          EOF

      # The commit the job's token names, not the default branch: the harness
      # that runs here is the one the role trusts.
      - name: Check out the harness
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          repository: ${{ steps.own.outputs.repo }}
          ref: ${{ steps.own.outputs.sha }}
          ssh-key: ${{ secrets.FACTORY_DEPLOY_KEY }}
"""),
    # The agent's file and tools came from the agents job, which read factory-repo's default branch: hold them
    # to the harness checked out above.
    ("""\
      - name: Check out the pull request's base
""", """\
      - name: Hold the agent to this harness
        env:
          AGENT_NAME: ${{ matrix.agent.name }}
          AGENT_FILE: ${{ matrix.agent.file }}
          AGENT_TOOLS: ${{ matrix.agent.tools }}
        run: |
          python3 - <<'EOF'
          import os
          import re
          import sys
          from pathlib import Path


          def fail(message):
              print("::error::" + message)
              sys.exit(1)


          name, file, tools = (os.environ.get(key, "") for key in ("AGENT_NAME", "AGENT_FILE", "AGENT_TOOLS"))
          if not re.fullmatch(r"[a-z0-9-]+", name):
              fail("{!r} isn't a skill's or an agent's name.".format(name))
          skill, agent = Path("harness/skills") / name / "SKILL.md", Path("harness/agents") / (name + ".md")
          path = skill if skill.is_file() else agent if agent.is_file() else None
          if path is None or file != path.as_posix():
              fail("{} isn't in this workflow's own harness as {}.".format(name, file))
          if tools != "Read,Grep,Glob":
              fail("The Bedrock review runs agents with Read, Grep and Glob only, not {}.".format(tools))
          lines, front = path.read_text().split("\\n"), []
          if lines[0].strip() == "---":
              for line in lines[1:]:
                  if line.strip() == "---":
                      break
                  front.append(line)
          if any(line.startswith("ci-shell:") for line in front):
              fail("{} has a ci-shell: line, which the Bedrock review doesn't run.".format(path))
          EOF

      - name: Check out the pull request's base
"""),
    # The CLI's own installer runs; no other package script does.
    ("""\
        run: npm install -g @anthropic-ai/claude-code@2.1.296
""", """\
        run: |
          npm install -g --ignore-scripts @anthropic-ai/claude-code@2.1.296
          cd "$(npm root -g)/@anthropic-ai/claude-code"
          env -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u ACTIONS_ID_TOKEN_REQUEST_URL node install.cjs
"""),
    # base/ is whatever branch the pull request targets, and anyone who can push a branch can target one of
    # their own, so its links go too: one could point the agent's Read at /proc. Its AGENTS.md stays: it's the
    # project's rules the prompt names.
    ("""\
          find head -path head/.git -prune -o -type l -exec rm -f {} +
""", """\
          find base -path base/.git -prune -o -type l -exec rm -f {} +
          find head -path head/.git -prune -o -type l -exec rm -f {} +
"""),
    # The CLI needs the AWS session, never the means to ask for another one.
    ("""\
          claude -p --max-turns 30 --restricted --strict-mcp-config --tools "$AGENT_TOOLS" \\
""", """\
          env -u ACTIONS_ID_TOKEN_REQUEST_TOKEN -u ACTIONS_ID_TOKEN_REQUEST_URL \\
            claude -p --max-turns 30 --restricted --strict-mcp-config --tools "$AGENT_TOOLS" \\
"""),
    # The role is assumed directly before the review, which runs on Bedrock with the caller's model.
    ("""\
      # Run from the workspace, so harness/, base/ and head/ are all inside
      # the confinement and nothing else on the runner is. The key sits in the
      # environment of the process the tools run in, and /proc is outside the
      # workspace, so a Read of /proc/self/environ is refused. The report's
      # fields reach the comment, so this step refuses one that contains
      # either credential: a backstop for one written out as it is, not a
      # guarantee against an encoded one, which is why the confinement matters
      # more. Each is checked only when set, since an empty pattern matches
      # every report. The tools are the agents job's: Read, Grep and Glob,
      # and the commands a ci-shell: line names.
      - name: Run the review-pr skill on Claude
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          AGENT_TOOLS: ${{ matrix.agent.tools }}
""", """\
      # The action trades the job's OIDC token for a session on the caller's
      # role and exports it to every later step, so it runs directly before
      # the review, and the step after the review empties it again. It holds
      # no secret. The session it asks for lasts 15 minutes; the role allows
      # up to its MaxSessionDuration to anything that asks itself.
      - name: Assume the review role on AWS
        uses: aws-actions/configure-aws-credentials@e1253824e5c10ff9df46874f81ed3ec929e19cfd # v6.3.0
        with:
          role-to-assume: ${{ inputs.aws-role-arn }}
          aws-region: ${{ inputs.aws-region }}
          role-duration-seconds: 900

      # Run from the workspace, so harness/, base/ and head/ are all inside
      # the confinement and nothing else on the runner is. The session sits in
      # the environment of the process the tools run in, and /proc is outside
      # the workspace, so a Read of /proc/self/environ is refused; the links
      # that could reach it are gone from base/ and head/, and the CLI runs
      # without the token-request values, so it can't ask for a session of its
      # own. Nonessential traffic is off, so nothing but Bedrock is called. The model is
      # the caller's, so Claude Code's own default, which may route through
      # another region, is never used. The report's fields reach the comment,
      # so this step refuses one that contains any of the session's values: a
      # backstop for one written out as it is, not a guarantee against an
      # encoded one, which is why the confinement matters more. The tools are
      # Read, Grep and Glob.
      - name: Run the review-pr skill on Claude
        env:
          CLAUDE_CODE_USE_BEDROCK: '1'
          CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1'
          ANTHROPIC_MODEL: ${{ inputs.aws-model }}
          ANTHROPIC_SMALL_FAST_MODEL: ${{ inputs.aws-model }}
          ANTHROPIC_DEFAULT_HAIKU_MODEL: ${{ inputs.aws-model }}
          AGENT_TOOLS: ${{ matrix.agent.tools }}
"""),
    ("""\
          if [ -n "$ANTHROPIC_API_KEY" ] && grep -qF -e "$ANTHROPIC_API_KEY" "$RUNNER_TEMP/report.json"; then
            leaked=true
          fi
          if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ] && grep -qF -e "$CLAUDE_CODE_OAUTH_TOKEN" "$RUNNER_TEMP/report.json"; then
            leaked=true
          fi
          if [ "$leaked" = true ]; then
            rm -f "$RUNNER_TEMP/report.json"
            echo "::error::The report contained the Claude credential, so it was not posted."
""", """\
          for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN ACTIONS_ID_TOKEN_REQUEST_TOKEN; do
            value="${!name}"
            if [ -n "$value" ] && grep -qF -e "$value" "$RUNNER_TEMP/report.json"; then
              leaked=true
            fi
          done
          if [ "$leaked" = true ]; then
            rm -f "$RUNNER_TEMP/report.json"
            echo "::error::The report contained the AWS session's credentials, so it was not posted."
"""),
    ("""\
      # The report is the model's, steered by a diff anyone who can open a pull
      # request can write, so it's read as data.""", """\
      # The AWS step exports its session to every step after it, so this one
      # empties those values for the schema check, the post and the threads.
      # It isn't forced to run after a failed review: the job ends there, and
      # the session expires 15 minutes after it was assumed.
      - name: Clear the AWS credentials
        run: |
          for name in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_REGION AWS_DEFAULT_REGION; do
            echo "$name=" >> "$GITHUB_ENV"
          done

      # The report is the model's, steered by a diff anyone who can open a pull
      # request can write, so it's read as data."""),
    ("\nname: Review pull request\n", "\nname: Review pull request on Bedrock\n"),
]


def build(text):
    """review-pr.yml's text with HEADER on top and each of EDITS made. Raises ValueError naming the first
    anchor that isn't there exactly once."""
    for number, (anchor, replacement) in enumerate(EDITS, 1):
        count = text.count(anchor)
        if count != 1:
            raise ValueError("edit {} of {}: its anchor is in review-pr.yml {} times, not once: {!r}".format(
                number, len(EDITS), count, anchor.strip().splitlines()[0]))
        text = text.replace(anchor, replacement)
    return HEADER + text


def main(argv):
    made = build(SOURCE.read_text())
    if argv[1:] == ["--check"]:
        if not TARGET.is_file() or TARGET.read_text() != made:
            print("{} isn't what scripts/bedrock_workflow.py makes from review-pr.yml: run "
                  "python3 scripts/bedrock_workflow.py".format(TARGET.relative_to(ROOT)))
            return 1
        print("{} is up to date".format(TARGET.relative_to(ROOT)))
        return 0
    if argv[1:]:
        print(__doc__)
        return 2
    TARGET.write_text(made)
    print("wrote {}".format(TARGET.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
