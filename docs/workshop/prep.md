# Running the workshop with your team

The checklist for whoever runs the [workshop](README.md) for a group, in person
or online. The full version takes a little over three hours. When you have
two, run it as below: every section stays, the
workflow material stays whole, and one person demos the loop instead of
everyone running their own.

## The two hours

| Start | Section | Slides | How |
|---|---|---|---|
| 0:00 | Opening, 1. Why a factory | 1 to 9 | 10 min. Spend it on slide 8: the factory runs workflows |
| 0:10 | 2. Your own clone | 10 to 12 | 5 min. A check only: setup happens before the day |
| 0:15 | 3. Connect your knowledge | 13 to 16 | 15 min. One person drives; the room asks the two questions |
| 0:30 | 4. Skills and workflows | 17 to 21 | 40 min. The skill 10, interviews in pairs 25, each pair's outcome 5 |
| 1:10 | 5. Your first motion | 23 to 26 | 25 min. You run one real issue through the loop, live |
| 1:35 | 6. Your first gate | 27 to 30 | 10 min. Walk the example gate refusing a commit |
| 1:45 | 7. What comes next | 31 to 36 | 15 min. The path, homework both ways, the next session booked |

Slide 22 is the full version's break. Skip it, or take five minutes from
section 4.

## A week before

- [ ] Send everyone [`handout.md`](handout.md), and ask each person to reply
      with the last line of `python3 scripts/check_setup.py`
- [ ] Ask each person to pick one piece of work they repeat: something that
      arrives, gets checked against rules, and goes to someone for sign-off.
      Section 4 interviews them about the last real time they did it
- [ ] Pick the knowledge source for section 3: one space, read-only, with no
      customer records in it. Check one person can read it
- [ ] Anyone on a personal Claude plan brings invented data only

## The night before

- [ ] Run one issue through the loop on your own sandbox, and keep its
      `.loop/loop.log`. If the live run is slow, walk this one instead
- [ ] Pick the issue you'll run live: small, real, and something a test can check
- [ ] Click through the deck once, in the format you'll present it

## On the day, before you start

- [ ] The deck open and screen sharing tested on it
- [ ] Your sandbox terminal and `/factory-floor` ready in a second window
- [ ] Online, breakout rooms set up for pairs
- [ ] The five finish lines somewhere everyone can see, to tick off live. The
      skills line gets two ticks: the skill, then the blueprint
- [ ] Recording only if everyone agreed beforehand

## In the room

- Interviews are about the last real time the work happened, never the general
  case. Each blueprint ends in build it, write the rules down first, or not a
  fit. The questions are in [`../building-workflows.md`](../building-workflows.md)
- No secrets on screen, in a prompt or in a ticket. Refer to them by name
- The loop opens the pull request; a person merges it, every time

## After

- [ ] A recap the same day, short enough to read on a phone, with what each
      side does next
- [ ] Each blueprint that ended in "build it" is the next session's work
