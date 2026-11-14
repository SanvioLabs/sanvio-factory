# What the agent never decides alone

The decisions below are never the agent's to make alone. Before any of these
steps, stop and name who decides it. Each row names the file where the rule
lives and doesn't restate it.

Where this page and the linked file disagree, the linked file wins.

| Decision | Who decides | Where the rule lives |
|---|---|---|
| Sending, emailing or publishing anything | A person, who sends it themselves | [`AGENTS.md`](../AGENTS.md), Rules |
| A connector call that sends, edits, deletes or shares | The person in the session, a yes to that one call | [`AGENTS.md`](../AGENTS.md), Rules |
| Merging a pull request | A person, unless the factory's owner has turned on `auto_merge` | [`AGENTS.md`](../AGENTS.md), first paragraph; [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md), *Merging, when you turn it on* |
| Turning on `auto_merge` | The factory's owner, never the agent | [`AGENTS.md`](../AGENTS.md), first paragraph |
| A price, a contract, a send to a customer | The person named under `## Who decides` in the company record | [`skills/orientation/COMPANY.example.md`](../skills/orientation/COMPANY.example.md), `## Who decides` |
| Using a data source marked `unconfirmed` | A person, in this session | [`skills/orientation/SKILL.md`](../skills/orientation/SKILL.md), step 4 |
| Editing a gate to make work pass | Nobody: it isn't done. Changing a gate is a person's deliberate change | [`AGENTS.md`](../AGENTS.md), *Done means the gate passes*; [`gates.md`](gates.md) |
| Writing a new rule from a lesson | The person, a yes to the rule as shown | [`skills/learn/SKILL.md`](../skills/learn/SKILL.md) |
| Turning off the usage log | The person running the session, unless an administrator's managed setting keeps it on | [`data-and-tools.md`](data-and-tools.md) |
| Turning off the loop's command sandbox | The factory's owner, in the factory's `loop.json` | [`HOW-IT-WORKS.md`](../HOW-IT-WORKS.md), `sandbox_commands` |
| Adding an AI tool or MCP server | Whoever agrees it with the customer, before any customer information reaches it | [`data-and-tools.md`](data-and-tools.md), *Approved tools* |
| Deploying to production | A person, a yes to that one deploy | [`deploying.md`](deploying.md), *Every deploy* |
| Deleting or overwriting data, test data included | A person, asked first | [`deploying.md`](deploying.md), *Never* |
