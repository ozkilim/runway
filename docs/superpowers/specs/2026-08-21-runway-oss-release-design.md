# runway — open-source cloud spend for your coding agent

**Date:** 2026-08-21
**Status:** approved

## What

An open-source repo (`runway`, MIT) that lets anyone see cloud credit + spend numbers
from inside their coding agent. Ported from the private `cloud-spend-dashboard`
project: CLI + provider modules + an agent skill, plus per-provider setup
walkthroughs.

## Goals

1. **5-minute AWS setup** for someone with Claude Code: clone → `./install.sh` →
   paste IAM policy → fill `~/.runway/config.yaml` → ask "what's my burn".
2. **Zero personal data**: no author-machine paths, usernames, keys, account IDs, or
   spend figures anywhere in code, docs, sample output, or git history. Fresh git
   history. (The GitHub URL contains the owner's username; nothing else does.)
3. **Contributor-friendly**: adding a provider = implement one class (~100 lines);
   CONTRIBUTING.md documents the interface with `aws.py` as reference.
4. **Agent-agnostic**: ships a Claude Code skill plus an AGENTS.md snippet usable by
   any coding agent.

## Repo layout

```
runway/
├── README.md              # pitch, sample output (FICTIONAL numbers), 60-sec quickstart,
│                          # provider status table, contributor call-to-action
├── LICENSE                # MIT
├── CONTRIBUTING.md        # base.Provider interface guide, "add a provider" walkthrough
├── install.sh             # venv + pip install + install skill with resolved paths
├── runway.py              # CLI entry (port of cloudspend.py)
├── render.py, utils.py
├── providers/
│   ├── base.py            # Provider ABC: fetch() -> ProviderResult
│   ├── aws.py             # Cost Explorer via boto3 — battle-tested
│   ├── azure.py           # Cost Management — works pay-as-you-go, blind for sponsorships
│   └── gcp.py             # BigQuery billing export — wired, needs testers
├── config.example.yaml    # placeholders only
├── skill/
│   ├── SKILL.md           # generic skill; install.sh writes resolved absolute paths
│   └── AGENTS.md          # copy-paste for Cursor/Codex/etc.
├── docs/setup/
│   ├── aws.md             # console clicks, minimal IAM policy JSON, credits page, CE gotchas
│   ├── azure.md           # app registration, role assignment, sponsorship blind spot
│   └── gcp.md             # service account, BigQuery export (no backfill warning)
├── requirements.txt
└── .gitignore             # config.yaml, .env, *.json creds, venv, __pycache__
```

## Key decisions

- **Config lives at `~/.runway/config.yaml`** (mode 600), never in the repo.
  Fields per provider: credentials + `credits`, `credits_as_of`, `expires` —
  manually entered from the console credits page because no cloud exposes remaining
  credit via API. `credits_as_of` is load-bearing (remaining = credits − drawdown
  since that date); docs carry a warning box.
- **CLI flags preserved:** none (table), `--json`, `--check`, `--provider X`.
- **Presentation philosophy preserved:** the script emits facts only — no runway
  verdicts, no burn-rate editorializing. The skill tells the agent: show the table,
  stop, add at most one line when something genuinely warrants it (cash charged,
  outlier month, staleness warning).
- **Honest provider maturity:** README status table (AWS ✅ / Azure ⚠️ / GCP 🧪).
  Weaknesses framed as contribution hooks.
- **install.sh behavior:** create `.venv` in repo, install requirements, create
  `~/.runway/` and copy `config.example.yaml` there if absent, install the skill to
  `~/.claude/skills/runway/SKILL.md` with the venv-python and repo paths substituted
  in, print next steps. Idempotent. Detect missing Claude Code gracefully (still
  print AGENTS.md instructions).
- **Sample output in README uses fictional numbers** (e.g. Acme-style $10,000 grant),
  never real spend.

## Out of scope (YAGNI)

- No PyPI packaging, no web dashboard (old app.py dropped), no forecast module,
  no CI beyond a lint/smoke GitHub Action (optional, may add later), no telemetry.

## Release checklist (part of implementation)

- Grep entire repo for the author's username, home paths, account IDs, real dollar
  figures, key material before first commit and again before push.
- Fresh `git init`; first commit is already-clean code.
- Create GitHub repo public with description + topics (cloud-costs, claude-code,
  agent-skills, finops, aws, devtools).
