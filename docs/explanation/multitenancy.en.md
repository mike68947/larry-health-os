<!-- translation-of: docs/explanation/multitenancy.md sha256:f8d2e2e3c9e3 -->
<!-- Machine translation by doc_agent --translate-intent; regenerated with the Russian page, do not edit by hand. -->

**English** · [Русский](multitenancy.md)

# Multi-user mode: tenant isolation, so that what belongs to one person does not end up in someone else's hands

## What changed

- **A new promise was added: a reminder belongs to the person's own channel.** The invariant `reminder_channel_belongs_to_person` was entered into the subsystem's registry with the status "holds".
- **What it means in practice.** A reminder goes only to the person's own channel: their CalDAV list taken from their secrets. The built-in Reminders app on the computer writes to the machine's own account, so this path is allowed only for the installation operator and only where it is technically possible.
- **How refusals behave.** A tenant without their own channel gets a loud refusal, not someone else's account. An operator without a channel gets a quiet "reminders are not connected".

**Updated:** 2026-10-31


## Why it exists

One and the same system serves two people: the owner and their partner. The code is shared, but each person's health data is their own. Each has their own database and their own secrets: keys, tokens, the address where messages should be sent. We call such a person, together with their database and secrets, a tenant.

The worst thing that can happen here is the loss of the boundary between people. It has already happened once. The modules that sent out notifications kept secrets right in the code, "hardwired" in advance. Because of this, hypotheses about the partner's health went to the owner. Not out of malice, but because the system silently substituted a "default" recipient.

Hence the subsystem's main rule: in multi-user mode, no process takes data or secrets "by default". Either it is told explicitly whose tenant it is, or it loudly refuses to work. A quiet "well, let it be the owner" is forbidden.

## What it does, in plain words

**It does not substitute secrets silently.** If the data belongs to a tenant and the folder with their secrets is not specified, the system does not hand over the owner's secrets "just in case". It refuses. This is called fail-closed: when in doubt, the door stays closed.

**It does not take data by default.** In multi-user mode, a process that has not been told whose data to take fails with a loud error. It does not pick up a tenant's data "by default".

**It separates two questions: "whose data is this" and "whose rights are these".** The data-origin check answers only the first question and never takes part in issuing secrets. The answer "this data belongs to the owner" must not by itself open someone else's tokens. These two questions were separated by a dedicated change (9e98d8d, 12 August 2026), because mixing them up was the cause of the incident with the partner's hypotheses.

**It looks for traces of leaks.** An integrity probe scans the databases of all tenants and looks in one for the "fingerprint" of another. If something has leaked, it will be noticed rather than remain unnoticed.

**It makes sure delivery goes to the right address.** The direct Telegram sending channels are checked by a completeness probe: each one takes its recipient either from the tenant resolver or is on a short list of the owner's service channels that carry no medical data. Bot channels also take their recipient from the resolver, which a check dated 11 July 2026 confirmed. The historical leak point, hypothesis delivery, now goes through tenant secrets.

**Reminders go to the person's own channel.** A reminder goes only to their own calendar (their own CalDAV list from their secrets). The built-in Reminders app on the computer writes to the machine's own account, and that account belongs to whoever installed the system. So this path is allowed only for the installation operator and only where it is technically possible. A single "judge" decides this, for both writing and reading. A tenant without their own channel gets a loud refusal, not someone else's account. An operator without a channel gets a quiet "reminders are not connected".

## What can honestly be said about its limits

**Open item: the shared text for both.** One of the promises is not yet closed (status "open"): the shared text of the weekly digest that both tenants read.

The design is as follows. The shared text goes out only when each tenant's own process, having checked against its own dictionary, has issued the verdict "pass". The verdict is stored as a file `<week>.gate.<label>.json` in the shared folder for the week. If any tenant's file shows "blocked" or is corrupted, the text goes to no one. The decision "send or wait" is made by the pure function `weekly_digest.due`. The bot calls it and `verdicts()` before sending, and the delivery mark is set only after the receipt.

But there is a caveat. Since 30 September, the tenants run in different environments: the owner in a container, the partner on the host. If the verdict of a tenant from the other environment has not yet landed in the folder, the system does not wait for it. This is the owner's decision of 5 October: "don't wait, if there are problems we'll deal with them". This means that for now this item cannot be considered closed: a situation is possible in which the shared text goes out without waiting for the verdict of the tenant from the other environment.

**The file-system boundary.** Isolation rests on data and secrets, not on the machine's files. If the bot is sent a file path, it is read with the rights of the machine's user, so the partner's bot is technically able to read the owner's file. This is a named boundary, the owner's decision of 24 September (the document-intake thread, see `document_intake`). The original premise: people sharing one machine trust each other, and if someone uses the system, that means they are trusted. The subsystem does not protect against distrust between people on the same computer.

The remaining promises are marked as holding. The record contains no separate caveats about conditions under which they were not checked, but it also contains no claim that they were checked under all possible conditions.

## Where it is in the system

- `secrets_paths.py` — this is where it is decided where a tenant's secrets and data come from, and where the refusals trigger: when the secrets folder is not specified and when there is no explicit tenant in multi-user mode.
- `subsystem_intent.yaml` — the subsystem's intent record: the rule, the promises (invariants) and their statuses, including the open item about the shared text.
- `document_intake` — an adjacent thread where the named boundary about reading files by a submitted path is recorded.
