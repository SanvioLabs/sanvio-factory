# Compliance

Read this when you write or review a change that stores or moves personal data,
adds or changes access or logging, adds a dependency or outside service,
changes deployment or infrastructure, widens what an agent does unattended,
lets outside text reach a prompt, changes who merges or decides, or changes
the model, the provider or an agent's instructions.

Most compliance findings are ordinary engineering questions nobody asked in
time: where the data goes, who can reach it, what the log records. This file
names the questions, and the control families an auditor would file them
under, so the answer is in the change before anyone has to ask for it.

## The baseline

The baseline is NIST SP 800-53 Rev. 5 (release 5.2.0). Its control families
are the vocabulary here: AC (access control), AU (audit and accountability),
CM (configuration management), IA (identification and authentication), SA
(system and services acquisition), SC (system and communications protection),
SI (system and information integrity) and SR (supply chain risk management).

For a change that carries AI risk, three companions sit beside SP 800-53: the
NIST AI RMF 1.0 (its GOVERN, MAP, MEASURE and MANAGE functions),
ISO/IEC 42001:2023 (its Annex A controls) and the OWASP Top 10 for LLM
Applications.
Name an OWASP risk by its name, such as prompt injection, not its number,
because the numbering differs between editions.

If `company/COMPANY.md` names a framework the company is held to (such as SOC 2,
HIPAA, PCI DSS or ISO 27001), keep it in view alongside this one and name its
clause where a change touches it. If it names none, ask the person whether one
applies before you assume there isn't. Don't quote from that file into a
tracked one.

## By kind of change

| Kind of change | Families to keep in mind | The question to answer before calling it done |
|---|---|---|
| Stores or moves personal data | SC, AC, SI | Where does it rest and travel, is it encrypted both ways, and who can read it? |
| Adds or changes access | AC, IA | Who can do this now who couldn't before, and what stops everyone else? |
| Adds or changes logging | AU, SI | Does it record who did what and when, with no secret or personal data in the record? |
| Adds a dependency or outside service | SA-9, SR, CM | Is it pinned and from a source we trust, and what does the outside service see? |
| Changes deployment or infrastructure | CM, SC, AC | Can it be traced to a reviewed commit and rolled back, with permissions no wider than the job? |
| Widens what an agent does unattended: a new tool, command, permission, path, network reach or token budget | AC-6, CM-7; OWASP excessive agency and unbounded consumption; AI RMF MANAGE 2.4; ISO 42001 A.6 | What can it now do with nobody watching, and what stops it or switches it off? |
| Lets text from outside reach a prompt: an issue, a pull request, a comment, a caller's repo, a web page or a file someone sends | SI-10, AC-4; OWASP prompt injection and improper output handling; AI RMF MEASURE 2; ISO 42001 A.6 | Who could have written that text, and what could it get the agent to do? |
| Changes who merges, approves or decides: `auto_merge`, the review rubric, a gate, or a step a person decides | AC-5; OWASP excessive agency; AI RMF GOVERN 3.2; ISO 42001 A.9 | Does a person still decide, and what enforces it when the agent decides otherwise? |
| Changes the model, the provider or an agent's instructions: a model id, an agent's file, steering, or a review brief | SA-9, CM-3; OWASP supply chain and misinformation; AI RMF GOVERN 6 and MEASURE 2; ISO 42001 A.10 | Is the provider on Approved tools, and did the evals that cover it run again? |

A change can be more than one kind. Answer each kind's question. Where you can
name the exact control (AC-3 for an access check, SC-8 for data in transit),
name it; the family is enough where you can't.

## What this is not

This is engineering guidance, not a formal SP 800-53A assessment or an
authorization. It helps a change arrive with its answers. It doesn't say a
system meets the standard.
