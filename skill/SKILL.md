---
name: runway
description: Show current cloud credit and spend numbers - how much credit was granted, how much is used, how much is left, when it expires, and where the money went. Use whenever the user asks about cloud spend, cloud costs, credits, AWS/Azure/GCP spend, "how much have I spent", "how much is left", "what's my burn", "what's my runway", "am I running out of credits", or invokes /runway. Pulls live from the cloud billing APIs - never answer these from memory or from earlier numbers in the conversation, they go stale.
---

# runway

Pulls live credit and spend facts from configured cloud providers and presents them.

## Run it

```bash
{{RUNWAY_PYTHON}} {{RUNWAY_REPO}}/runway.py
```

Use that interpreter by absolute path — it is the project venv with the cloud SDKs
installed; the system python may lack them. Never shell out to `aws`, `az`, or
`gcloud`; the SDKs are used deliberately.

Flags:
- *(none)* — formatted table. This is what you show the user.
- `--json` — raw payload. Use when the user asks a follow-up you need to compute from
  (per-service totals, month-over-month comparisons, "what changed").
- `--check` — credentials smoke test, no cost data.
- `--provider aws` — limit to one provider (`aws`, `azure`, or `gcp`).

## Presenting the result

**Show the output and stop.** The user wants numbers, not narration. Do not restate
figures that are already on screen, do not summarise the table back, do not add a
preamble. The script emits facts only — no runway estimates, no burn rate, no
thresholds, no verdicts — and that terseness is deliberate at both layers.

Add **at most one line** underneath, and only when something genuinely warrants it:

- **`cash` > $0 in any month** — credits ran short and real money was charged.
- **A month far outside the others** — an outlier against the baseline. Name the
  service responsible from `by_service_90d`.
- **`warning` field set** — e.g. `credits_as_of` predates billing-data retention,
  so the balance may be overstated.

Otherwise say nothing. Refunds and tax in `other` are already marked inline in the
table and need no comment.

Never invent a runway figure unless asked. If asked, give a range and state the
assumption — burn is volatile.

## Config

`~/.runway/config.yaml`, mode 600. Holds credentials plus, per provider:
`credits` (grant total), `credits_as_of` (the date that figure was true), `expires`.

`credits_as_of` is load-bearing: remaining is computed as
`credits − drawdown since credits_as_of`. Getting it wrong silently produces a
wrong balance. No cloud exposes a remaining-credit balance via API, so `credits`
and `expires` are typed in from the console's Credits page. If the user says their
grant changed, update that file rather than adjusting numbers by hand.

## Setup / adding a provider

Per-provider walkthroughs live in `{{RUNWAY_REPO}}/docs/setup/` (aws.md, azure.md,
gcp.md). If the user wants to hook up a new cloud account, follow the relevant doc
step by step. Providers render as `not configured` until enabled and never block
the others.

## Errors

Failures are per-provider and never abort the run. Known causes are reported with a
hint attached. Secrets are scrubbed from all error output — keep it that way.
