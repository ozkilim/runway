#!/usr/bin/env python3
"""runway - pull cloud credit/spend facts into one place.

Emits facts only. No forecasting, no thresholds, no verdicts: interpretation is the
caller's job. `--json` is the primary contract; the table is for humans in a terminal.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".runway" / "config.yaml"
KNOWN_PROVIDERS = ("aws", "azure", "gcp")

# Failures that have a specific, actionable cause.
ERROR_HINTS = {
    "AccessDeniedException": (
        "IAM policy missing ce:GetCostAndUsage, OR the account-level switch "
        "'IAM user and role access to Billing information' is off "
        "(root user -> Account settings)."
    ),
    "DataUnavailableException": (
        "Cost Explorer is not enabled, or is still backfilling (up to 24h "
        "after first enable)."
    ),
    "InvalidClientTokenId": "Access key id is not valid.",
    "SignatureDoesNotMatch": "Secret access key is wrong (check for stray whitespace).",
    "UnrecognizedClientException": "Credentials rejected by AWS.",
    "ExpiredTokenException": "Credentials have expired.",
    "ModuleNotFoundError": (
        "A provider SDK is not installed. AWS needs `boto3`; Azure needs "
        "`azure-identity azure-mgmt-costmanagement`; GCP needs "
        "`google-cloud-bigquery`. Install into the venv this script runs from."
    ),
}


def collect_secrets(cfg: dict) -> list[str]:
    """Every credential-ish value, so it can be scrubbed from error output."""
    found = []
    for provider in cfg.values():
        if not isinstance(provider, dict):
            continue
        for key, value in provider.items():
            if not isinstance(value, str) or len(value) < 8:
                continue
            if any(t in key.lower() for t in ("secret", "key", "password", "token")):
                found.append(value)
    return found


def sanitize(text, secrets: list[str]) -> str:
    out = str(text)
    for s in secrets:
        out = out.replace(s, "<REDACTED>")
    return out


def describe_error(exc, secrets: list[str]) -> dict:
    code = type(exc).__name__
    message = sanitize(exc, secrets)
    try:  # botocore ClientError carries a structured code
        err = exc.response["Error"]
        code = err.get("Code", code)
        message = sanitize(err.get("Message", message), secrets)
    except (AttributeError, KeyError, TypeError):
        pass
    return {
        "status": "error",
        "error_code": code,
        "error": message,
        "hint": ERROR_HINTS.get(code),
    }


def load_config(path: Path) -> dict:
    import yaml

    if not path.exists():
        sys.exit(
            f"No config at {path}\n"
            f"Create it with:\n"
            f"  mkdir -p {path.parent} && chmod 700 {path.parent}\n"
            f"  cp config.example.yaml {path} && chmod 600 {path}\n"
            f"then follow docs/setup/<provider>.md to fill it in."
        )
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def build_provider(name: str, cfg: dict):
    if name == "aws":
        from providers.aws import AWSProvider

        return AWSProvider(cfg)
    if name == "azure":
        from providers.azure import AzureProvider

        return AzureProvider(cfg)
    if name == "gcp":
        from providers.gcp import GCPProvider

        return GCPProvider(cfg)
    raise ValueError(f"unknown provider {name}")


def gather(config: dict, only: str | None = None) -> dict:
    secrets = collect_secrets(config)
    providers: dict[str, dict] = {}

    for name in KNOWN_PROVIDERS:
        if only and name != only:
            continue
        cfg = config.get(name) or {}
        if not cfg.get("enabled"):
            providers[name] = {"status": "not_configured"}
            continue
        # One provider failing must never take down the others.
        try:
            providers[name] = build_provider(name, cfg).snapshot()
        except Exception as exc:  # noqa: BLE001 - deliberate isolation boundary
            providers[name] = describe_error(exc, secrets)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "providers": providers,
    }


def run_check(config: dict) -> int:
    """Credentials smoke test. Prints nothing sensitive."""
    secrets = collect_secrets(config)
    failures = 0
    for name in KNOWN_PROVIDERS:
        cfg = config.get(name) or {}
        if not cfg.get("enabled"):
            print(f"  {name:<6} skipped (not enabled)")
            continue
        try:
            provider = build_provider(name, cfg)
            ok = provider.test_connection()
            tail = getattr(provider, "account_tail", lambda: None)()
            where = f" account ...{tail}" if tail else ""
            print(f"  {name:<6} {'OK' if ok else 'FAILED'}{where}")
            failures += 0 if ok else 1
        except Exception as exc:  # noqa: BLE001
            info = describe_error(exc, secrets)
            print(f"  {name:<6} FAILED [{info['error_code']}] {info['error']}")
            if info.get("hint"):
                print(f"         hint: {info['hint']}")
            failures += 1
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Cloud credit and spend snapshot")
    ap.add_argument("--json", action="store_true", help="emit raw JSON (primary contract)")
    ap.add_argument("--check", action="store_true", help="credentials smoke test only")
    ap.add_argument("--provider", choices=KNOWN_PROVIDERS, help="limit to one provider")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = ap.parse_args()

    config = load_config(args.config)

    if args.check:
        return run_check(config)

    payload = gather(config, only=args.provider)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        from render import render

        print(render(payload))

    return 0 if any(
        p.get("status") == "ok" for p in payload["providers"].values()
    ) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
