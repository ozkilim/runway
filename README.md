# 🛫 runway

**See your cloud runway without leaving your coding agent.**

You're a CTO / VP Eng / founder with cloud credits burning down. The billing
console is four logins away and lies to you anyway (credit-funded accounts read
$0.00 in the obvious places). runway pulls live credit + spend facts from the
cloud billing APIs and puts them one question away from wherever you already are:

```
you:    what's my burn?

agent:    CLOUD SPEND                                          2026-08-21 09:14

          AWS  ...4242
            granted  $10,000.00    used   $6,120.40 (61.2%)    left   $3,879.60 (38.8%)
            since    2026-01-01    expires  2027-06-30 (313d)    cash $0.00
          90d   Bedrock $2,911.07 | EC2 $801.22 | S3 $175.65 | VPC $10.79
          mo    2026-02 $310.55 | 2026-03 $334.10 | 2026-04 $381.90 | 2026-05 $492.03
                2026-06 $2,940.12 | 2026-07 $421.25 | 2026-08 $240.45*

          azure, gcp: not configured

          The June spike was Bedrock — $2,911 of the 90-day total.
```

Facts only. No forecasts, no traffic lights, no "insights". Your agent reads the
same numbers you do and only speaks up when something genuinely warrants it.

## Quickstart (5 minutes for AWS)

```bash
git clone https://github.com/ozkilim/runway.git
cd runway
./install.sh
```

Then follow [docs/setup/aws.md](docs/setup/aws.md) — create a read-only IAM user
(minimal policy JSON included, copy-paste), read your credit balance off the
console once, fill in `~/.runway/config.yaml`, and:

```bash
.venv/bin/python runway.py --check   # credentials smoke test
.venv/bin/python runway.py           # your numbers
```

If you use **Claude Code**, `install.sh` already installed the skill — just ask
*"what's my burn?"*. Any other agent (Cursor, Codex, Windsurf, ...): paste
[skill/AGENTS.md](skill/AGENTS.md) into your agent's instructions.

## Providers

| Provider | Status | Notes |
|---|---|---|
| **AWS** | ✅ battle-tested | Cost Explorer, true credit drawdown via record types |
| **Azure** | ⚠️ partial | Works for pay-as-you-go / EA. **Blind for sponsorship offers** — their usage never reaches the API; runway refuses to guess ([why](docs/setup/azure.md)) |
| **GCP** | 🧪 needs testers | BigQuery billing export, true credit records. Wired, unverified against a real account — [be the first](docs/setup/gcp.md) |
| Yours? | 🙌 | ~150 lines to add one — see [CONTRIBUTING.md](CONTRIBUTING.md) |

## Design principles

These are what make the numbers trustworthy — hold new providers to them:

1. **Facts only.** The tool emits what happened. Interpretation, forecasting, and
   panic are the reader's job (or their agent's, sparingly).
2. **UNKNOWN beats wrong.** If a number can't be measured honestly, it renders as
   `UNKNOWN` with the reason attached — never a confident $0.00.
3. **Credits are first-class.** Credit-funded accounts are the norm for startups,
   and every cloud console handles them badly. runway is explicit about
   granted / used / remaining / cash-beyond-credits.
4. **One manual read, then automation.** No cloud exposes remaining credit via
   API. You read the grant off the console once (`credits`, `credits_as_of`,
   `expires`); runway measures drawdown from that anchor forever after.
5. **Secrets never leave.** Read-only credentials, config at `~/.runway/` (never
   in the repo), secrets scrubbed from all error output.
6. **One provider failing never takes down the others.**

## CLI

```
runway.py            formatted table (what humans read)
runway.py --json     raw payload (what agents compute from)
runway.py --check    credentials smoke test, no cost data
runway.py --provider aws|azure|gcp
runway.py --config /path/to/config.yaml
```

## FAQ

**Why not just open the billing console?** You will not. That's the whole point.

**Why is `credits_as_of` so important?** Remaining = credits − drawdown since that
date. The console told you a balance on a specific day; measure from any other day
and the answer is silently wrong. See the [config comments](config.example.yaml).

**Does this cost anything to run?** AWS Cost Explorer API: ~$0.05/run. Azure/GCP:
effectively free.

**Is it safe?** The credentials you create are read-only cost aggregates — they
can't see resources or data, and can't spend money. Blast radius is "someone
learns your bill".

## Contributing

Adding a provider is the most valuable contribution — Oracle, Hetzner,
DigitalOcean, Cloudflare, Vercel, Modal, RunPod, Lambda... anywhere burn hides.
See [CONTRIBUTING.md](CONTRIBUTING.md): one class, two methods, ~150 lines, with
[`providers/aws.py`](providers/aws.py) as the reference.

MIT licensed.
