# Contributing

The most wanted contributions, in order:

1. **A GCP test report.** The provider is wired but unverified against a real
   account. Run it, open an issue saying what happened — that's it.
2. **A new provider.** Oracle, Hetzner, DigitalOcean, Cloudflare, Vercel, Modal,
   RunPod, Lambda Labs, Scaleway... anywhere burn hides.
3. **A sponsorship-Azure workaround.** If you know any API path to
   microsoftazuresponsorships.com balances, open an issue immediately.
4. Setup-doc fixes — console UIs drift; a corrected click-path is a real PR.

## Adding a provider

One file in `providers/`, one class, two required methods. Read
[`providers/base.py`](providers/base.py) for the contract and
[`providers/aws.py`](providers/aws.py) as the reference implementation
(~150 lines). Then:

1. **`providers/<name>.py`** — subclass `CloudProvider`, implement
   `test_connection()` (cheap real API call) and `snapshot()` (the fact payload —
   required keys are documented on the ABC). Import the cloud SDK **lazily inside
   methods**, never at module top level, so a missing SDK for your cloud can't
   break anyone else's run.
2. **`runway.py`** — add the name to `KNOWN_PROVIDERS` and a branch in
   `build_provider()`. Add provider-specific error hints to `ERROR_HINTS` if the
   SDK raises identifiable exceptions.
3. **`config.example.yaml`** — add a disabled-by-default block with placeholder
   credentials and the shared keys (`credits`, `credits_as_of`, `expires`).
4. **`docs/setup/<name>.md`** — the step-by-step: exact console clicks, a minimal
   read-only credential (least privilege, paste-ready), where the credits page is,
   and every gotcha you hit. The setup doc is half the value of a provider.
5. **`requirements.txt`** — add the SDK as a commented-out optional line.
6. **README** — add a row to the provider table with an honest status badge.

### The honesty rules (non-negotiable)

These are what make runway's numbers trustworthy:

- **Never report a number you didn't measure.** If drawdown can't be measured,
  return `None` for `credits_used` / `credits_remaining` — it renders as
  `UNKNOWN` — and say why in `warning`. A confident wrong balance is the one
  unforgivable bug (see the Azure sponsorship case in `providers/azure.py`).
- **An empty API result is not evidence of zero spend.** Distinguish "measured
  $0.00" from "nothing came back".
- **Derived ≠ reported.** If a figure is inferred rather than read from the
  provider's own records (like Azure's derived credit use), the `warning` field
  must say so.
- **Facts only.** No forecasting, no thresholds, no color-coding, no verdicts in
  the payload or the renderer.
- **Secrets are scrubbed** from every error path (`collect_secrets`/`sanitize` in
  `runway.py` handles config values — keep new secret-shaped config keys matching
  its patterns: `*secret*`, `*key*`, `*password*`, `*token*`).
- **Read-only credentials only.** Setup docs must create the least-privileged
  credential that can do the job, and say what its blast radius is.

### Style

- Python 3.10+, stdlib + the cloud SDK only. No pandas, no requests, no
  frameworks.
- Comments explain *why* (API quirks, honesty decisions), not *what*.
- Match the existing code: small module, section markers, provider isolated
  behind the ABC.

## Testing your provider

There's no mocked test suite yet (contributions welcome) — providers are
validated against real accounts:

```bash
.venv/bin/python runway.py --check              # credentials
.venv/bin/python runway.py --provider <name>    # table
.venv/bin/python runway.py --json               # payload keys complete?
```

Sanity-check the numbers against the provider's own console before opening the
PR, and say in the PR description which account type you verified against
(credit-funded vs pay-as-you-go matters a lot).
