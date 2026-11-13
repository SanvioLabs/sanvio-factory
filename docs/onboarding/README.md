# Onboarding cards

Six one-page cards for getting a team onto the factory, one for each session,
from the first commands to a loop that runs without anyone driving it. Each ends
with what to do before the next card. Hand people the PDF; it's one file, with a
contents page and the six cards.

| Card | What it covers |
|---|---|
| 1 · Getting started | How to work with it, the setup that has to be right, and the commands you'll use every day |
| 2 · Knowledge and skills | Connect one source of your own knowledge, write your first skill, and vet someone else's |
| 3 · First motion | One real task from ticket to a pull request a person merged, through the loop |
| 4 · Gates and guards | Turn the agent's real mistakes into rules and checks that block |
| 5 · Specs | Move up from tasks to features: write, challenge, plan, build and review a spec |
| 6 · Team and your loop | Bring the team in, keep a sprint rhythm, and let your loop run on its own |

[`onboarding-cards.html`](onboarding-cards.html) is the source and [`onboarding-cards.pdf`](onboarding-cards.pdf) is built from
it. Edit the HTML, then rebuild the PDF so the two match:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --no-pdf-header-footer \
  --print-to-pdf="$PWD/docs/onboarding/onboarding-cards.pdf" "file://$PWD/docs/onboarding/onboarding-cards.html"
```

Any Chromium browser works; on Linux it's `chromium --headless` with the same
flags. Keep each card to one letter page: the PDF should have seven.

When a skill is added, renamed or removed, check the cards name it the way the
repo does.
