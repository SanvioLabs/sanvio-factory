# Standup answers

One file, `answers.jsonl`, written by [`skills/standup/`](../../skills/standup/): one line
per answer given in a standup, naming a GitHub or loop item, the date and the pick. The
next standup reads it so that an item already marked done or dropped isn't asked about
again. It is gitignored, so it stays on the machine that wrote it; only this README is
tracked.

It holds no email subjects, senders, meeting titles or free-text answers. Delete it at
any time; the next standup starts fresh.
