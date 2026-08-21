# runway — snippet for any coding agent

Claude Code users don't need this file — `install.sh` installs the skill
automatically. For any other agent (Cursor, Codex, Windsurf, Aider, ...), paste the
block below into your agent's instructions file (`AGENTS.md`, `.cursorrules`,
`CONVENTIONS.md`, whatever your tool reads), replacing the two paths with the ones
`install.sh` printed.

---

## Cloud spend ("runway")

When I ask about cloud spend, cloud costs, credits, burn, or runway, run:

```
<REPO_PATH>/.venv/bin/python <REPO_PATH>/runway.py
```

and show me the table it prints. Rules:

- Always run it fresh — never answer spend questions from memory or from earlier
  numbers in the conversation; they go stale.
- Show the output and stop. No preamble, no restating figures, no summary.
- Add at most one line underneath, only if something genuinely warrants it:
  real cash charged beyond credits, one month far outside the baseline (name the
  service responsible), or a data-quality warning in the output.
- Never invent a "months of runway left" figure unless I explicitly ask; if I do,
  give a range and state the assumption.
- `--json` gives the raw payload for follow-up computation. `--check` smoke-tests
  credentials. `--provider aws|azure|gcp` limits to one cloud.
- Config lives at `~/.runway/config.yaml` (mode 600). Setup guides:
  `<REPO_PATH>/docs/setup/`.
- Never shell out to `aws`, `az`, or `gcloud` for this — the script uses the SDKs
  deliberately.
