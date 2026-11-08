# Maintaining the starter

For whoever releases the starter itself. A copy of the harness needs none of
this, and most can't reach the repo it names.

## Factories, against GitHub

The tests answer each `gh` call from a fake that matches its exact arguments
and never sees a real reply, so a change in the shape of what GitHub sends
back passes them. Before a release that changes [`scripts/factories.py`](../scripts/factories.py),
[`scripts/factory_checks.py`](../scripts/factory_checks.py) or [`scripts/forge.py`](../scripts/forge.py), run `doctor`
on the standing probe.

It holds only when all of these do:

- You can read `SanvioLabs/fork-check-probe`.
- Pull request #2 there is open, from a fork, and closes an issue in the
  probe.
- The probe's default branch requires at least one status check.
- The account that opened #2 has admin access to the probe, so its checks
  read `checks pass, not independent`.
- There's no `changes needed` review comment from you on #2's head.
- `factories.json` at the harness root names one step whose `factory_login`
  is the account that opened #2.

Then run:

```bash
python3 scripts/factories.py doctor --repo SanvioLabs/fork-check-probe --pr 2
```

It passes when it exits 0 with every reply usable and its `what status says`
line names `checks pass, not independent`, the required checks' result there.
With no review of its head from you, doctor reads it as ready and says so,
so the checks are read either way. doctor never gives a merge: `status` does,
for a run. doctor exits 0 for
`no required check` and `checks failing` too, so the line is what's checked,
not the exit alone.

Anything else blocks the release. Read the call it names: either GitHub's
answer changed shape, and the scripts need to follow it before the release, or
one of the conditions above no longer holds, and it's put back and run again.

## The review, against GitHub

doctor never runs `loop.py`, so it doesn't cover `loop.py review --pr`: the
post, the comment it edits, and the jq that tells its own comment from
anyone else's. Before a release that changes `review --pr` or `post_review`,
run it once on a scratch pull request in the probe, and leave #2 alone:

1. Clone the probe under [`projects/`](../projects/), with an origin on github.com as
   [`factories/README.md`](../factories/README.md)'s *github.com only* says, and give the clone a
   `loop.json` the loop reads its tests from, left uncommitted:
   `{"test_command": "python3 -m unittest discover -s tests -v"}`.
2. Open a pull request there from a new branch with one small commit, and run
   `python3 scripts/loop.py review --pr <N> --project projects/fork-check-probe`.
   It passes when it prints one JSON line naming the head and base, and the
   pull request carries one comment from you that starts with the review
   marker and the agent's header, and ends with the trailer naming that head.
3. Push a second commit, wait until
   `gh pr view <N> --repo SanvioLabs/fork-check-probe --json headRefOid` shows
   it, and run it again: right after a push GitHub can still give the old head,
   and the review then skips it as already reviewed. It passes when the same
   comment now names the new head, and there's still one.
4. Post a send-back the way `factories.py resend --because` writes one, from
   the harness root, with the head from step 3:
   `python3 -c 'import sys; sys.path.insert(0, "scripts"); import loop; print(loop.review_comment("A person sent this back.\n\nVERDICT: changes needed", sys.argv[1], header="A person sent this back to the factory, after reading the review."))' <HEAD> > send-back.md`,
   then `gh pr comment <N> --repo SanvioLabs/fork-check-probe --body-file send-back.md`
   and delete `send-back.md`. Push a third commit, wait for it as in step 3,
   and run the review again. It passes when the send-back is as you posted
   it, the review's own comment is the one that now names the third commit,
   and there's still one of each.
5. Close the pull request and delete its branch.
