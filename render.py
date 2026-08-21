"""Compact terminal rendering. Facts only - no thresholds, no verdicts, no forecasts."""

import re
from datetime import date

WIDTH = 96

# Long AWS service names carry no extra information at a glance.
_SHORTEN = [
    (r"^Claude (.+?) \(Amazon Bedrock Edition\)$", r"\1"),
    (r"^Amazon Elastic Compute Cloud - Compute$", "EC2"),
    (r"^EC2 - Other$", "EC2-Other"),
    (r"^Amazon Simple Storage Service$", "S3"),
    (r"^Amazon Virtual Private Cloud$", "VPC"),
    (r"^Amazon Relational Database Service$", "RDS"),
    (r"^AWS ", ""),
    (r"^Amazon ", ""),
]


def money(x) -> str:
    if x is None:
        return "-"
    if abs(x) < 0.005:  # kill negative zero from float residue
        x = 0.0
    return f"${x:,.2f}"


def short(name: str) -> str:
    for pattern, repl in _SHORTEN:
        new = re.sub(pattern, repl, name)
        if new != name:
            return new.strip()
    return name


def _days(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = (date.fromisoformat(iso) - date.today()).days
    except ValueError:
        return ""
    return f"({d:,}d)" if d >= 0 else f"({abs(d):,}d ago)"


def _flow(label: str, items: list[str], indent: int = 8) -> list[str]:
    """Wrap ' | '-joined items, label on the first line only.

    The separator must not appear inside item text - AWS service names such as
    'EC2 - Other' make a ' - ' separator ambiguous.
    """
    lines, current = [], f"  {label:<{indent - 2}}"
    prefix_blank = " " * indent
    for i, item in enumerate(items):
        candidate = current + ("" if current.strip() in ("", label) else " | ") + item
        if len(candidate) > WIDTH and current.strip() not in ("", label):
            lines.append(current)
            current = prefix_blank + item
        else:
            current = candidate
    if current.strip():
        lines.append(current)
    return lines


def render_provider(name: str, p: dict) -> list[str]:
    status = p.get("status")
    if status == "error":
        head = f"  {name}  ERROR [{p.get('error_code', '?')}] {p.get('error', '')}"
        out = [head[:WIDTH]]
        if p.get("hint"):
            out.append(f"        hint: {p['hint']}")
        return out
    if status != "ok":
        return [f"  {name.lower():<7}{str(status).replace('_', ' ')}"]

    granted = p.get("credits_granted")
    used = p.get("credits_used")
    left = p.get("credits_remaining")
    cash = p.get("cash_charged")

    tail = p.get("account_tail")
    L = [f"  {name}" + (f"  ...{tail}" if tail else "")]
    if used is None:
        # The provider could not measure drawdown. Showing $0.00 used here would
        # be read as "nothing spent" rather than "nothing known".
        L.append(
            f"    granted {money(granted):>11}"
            f"    used {'UNKNOWN':>11}"
            f"    left {'UNKNOWN':>11}"
        )
    elif granted:
        # Percentages are only meaningful against a known grant. Without one,
        # "left $0.00 (100.0%)" would read as a real balance rather than a gap.
        pct = used / granted * 100
        L.append(
            f"    granted {money(granted):>11}"
            f"    used {money(used):>11} ({pct:.1f}%)"
            f"    left {money(left or 0.0):>11} ({100 - pct:.1f}%)"
        )
    else:
        L.append(
            f"    granted {'not set':>11}"
            f"    used {money(used):>11}"
            f"    left {'unknown':>11}"
        )
    cash_note = "  <-- charged beyond credits" if (cash or 0) > 0.005 else ""
    L.append(
        f"    since   {p.get('credits_as_of', '?'):>11}"
        f"    expires  {str(p.get('expires') or '-')} {_days(p.get('expires'))}"
        f"    cash {money(cash)}{cash_note}"
    )
    if p.get("warning"):
        L.append(f"    ! {p['warning']}")

    services = p.get("by_service_90d") or []
    if services:
        L += _flow("90d", [f"{short(s['service'])} {money(s['usage'])}" for s in services])

    months = p.get("monthly") or []
    if months:
        items = []
        for m in months:
            item = f"{m['month']} {money(m['usage'])}"
            if (m.get("cash") or 0) > 0.005:
                item += f" (cash {money(m['cash'])})"
            elif "Refund" in (m.get("other") or {}):
                item += " (refunded)"
            elif m.get("estimated"):
                item += "*"
            items.append(item)
        L += _flow("mo", items)
    return L


def render(payload: dict) -> str:
    ts = payload.get("generated_at", "")[:16].replace("T", " ")
    out = ["", f"  CLOUD SPEND{ts:>{WIDTH - 13}}", ""]

    providers = payload.get("providers", {})
    ok = [(k, v) for k, v in providers.items() if v.get("status") == "ok"]
    rest = [(k, v) for k, v in providers.items() if v.get("status") != "ok"]

    for name, p in ok:
        out += render_provider(name.upper(), p) + [""]

    if len(ok) > 1:
        # Only providers that actually measured a drawdown may contribute. Adding
        # a known grant with an unmeasured spend inflates 'left' across the fleet.
        counted = [(n, p) for n, p in ok if p.get("credits_used") is not None]
        excluded = [n for n, p in ok if p.get("credits_used") is None]
        if counted:
            g = sum(p.get("credits_granted") or 0 for _, p in counted)
            u = sum(p.get("credits_used") or 0 for _, p in counted)
            r = sum(p.get("credits_remaining") or 0 for _, p in counted)
            line = f"  TOTAL   granted {money(g)}   used {money(u)}   left {money(r)}"
            if excluded:
                line += f"   (excludes {', '.join(sorted(excluded))}: unmeasured)"
            out += [line, ""]

    errors = [x for x in rest if x[1].get("status") == "error"]
    skipped = [x for x in rest if x[1].get("status") != "error"]
    for name, p in errors:
        out += render_provider(name.upper(), p)
    if skipped:
        out.append("  " + ", ".join(n for n, _ in skipped) + ": not configured")
    out.append("")
    return "\n".join(out)
