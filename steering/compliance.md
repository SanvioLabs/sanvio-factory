# Compliance

Read this when you write or review a change that stores or moves personal data,
adds or changes access or logging, adds a dependency or outside service, or
changes deployment or infrastructure.

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

A change can be more than one kind. Answer each kind's question. Where you can
name the exact control (AC-3 for an access check, SC-8 for data in transit),
name it; the family is enough where you can't.

## What this is not

This is engineering guidance, not a formal SP 800-53A assessment or an
authorization. It helps a change arrive with its answers. It doesn't say a
system meets the standard.
