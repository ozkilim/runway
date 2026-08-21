"""Azure Cost Management provider.

Status: works for pay-as-you-go / EA subscriptions; BLIND for sponsorship offers.

Two things differ from AWS and shape everything below:

1. Azure has no RECORD_TYPE dimension. AWS can ask Cost Explorer for the `Credit`
   records directly and read true credit drawdown; Azure's ActualCost is a single
   undifferentiated number. `credits_used` here is therefore *derived* (cumulative
   cost since credits_as_of), not reported, and snapshot() says so in `warning`.

2. Sponsorship credit balances are not in the ARM billing API at all - they live
   only at microsoftazuresponsorships.com. So `credits` must be typed into the
   config by hand; nothing can look it up. Worse, sponsorship *usage* often never
   reaches Cost Management either: the API returns HTTP 200 with zero rows. When
   that happens this provider refuses to report a balance rather than claim the
   full grant is still available.

Custom timeframes are also capped at 1 year per request, so long windows are
chunked and summed rather than issued as one query.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
import time

from .base import CloudProvider, as_date, months_back

CRED_KEYS = ("tenant_id", "client_id", "client_secret", "subscription_id")

# Azure rejects custom ranges over 1 year; stay comfortably inside it.
MAX_SPAN_DAYS = 360

# Cost Management throttles aggressively per-scope and a single snapshot issues
# several queries, so 429 is an expected condition here rather than an outage.
RETRY_ATTEMPTS = 4
RETRY_BASE_SECONDS = 5
_RETRY_AFTER_HEADERS = (
    "Retry-After",
    "x-ms-ratelimit-microsoft.costmanagement-entity-retry-after",
)

# Column names Azure uses for the cost measure, most-preferred first.
_COST_NAMES = ("costusd", "pretaxcostusd", "cost", "pretaxcost")
_DATE_NAMES = ("usagedate", "billingmonth", "date")
_SERVICE_NAMES = ("servicename", "consumedservice", "metercategory")


def parse_credentials_file(path: Path) -> dict:
    """Read `key = value` lines out of a free-form credentials note.

    The file is mostly prose; only the four keys we care about are extracted, and
    only the first occurrence of each wins so that a later mention inside a comment
    cannot silently override the real value. Values are NOT stripped of leading
    punctuation - Azure client secrets can legitimately begin with '.' or '~'.
    """
    found: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if key in CRED_KEYS and key not in found:
            value = value.strip()
            # Tolerate an inline trailing comment, but only when clearly separated,
            # so a '#' inside a secret is preserved.
            if "  #" in value:
                value = value.split("  #")[0].strip()
            if value:
                found[key] = value.strip("'\"")
    return found


class AzureProvider(CloudProvider):
    def __init__(self, config: dict):
        super().__init__("Azure", config)
        self._client = None
        self._resolved = None

    # -------------------------------------------------------------- credentials
    def _creds(self) -> dict:
        """Config values win; anything missing is filled from credentials_file."""
        if self._resolved is not None:
            return self._resolved

        resolved = {k: self.config[k] for k in CRED_KEYS if self.config.get(k)}

        cred_file = self.config.get("credentials_file")
        if cred_file and len(resolved) < len(CRED_KEYS):
            path = Path(cred_file).expanduser()
            if not path.exists():
                raise FileNotFoundError(f"credentials_file not found: {path}")
            for key, value in parse_credentials_file(path).items():
                resolved.setdefault(key, value)

        missing = [k for k in CRED_KEYS if not resolved.get(k)]
        if missing:
            raise KeyError(
                f"azure credentials incomplete, missing: {', '.join(missing)} "
                f"(set them in config.yaml or in credentials_file)"
            )
        self._resolved = resolved
        return resolved

    def _get_client(self):
        if self._client is None:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.costmanagement import CostManagementClient

            c = self._creds()
            credential = ClientSecretCredential(
                tenant_id=c["tenant_id"],
                client_id=c["client_id"],
                client_secret=c["client_secret"],
            )
            self._client = CostManagementClient(credential)
        return self._client

    def _scope(self) -> str:
        return f"/subscriptions/{self._creds()['subscription_id']}"

    def account_tail(self) -> str:
        try:
            return self._creds()["subscription_id"][-4:]
        except Exception:
            return "????"

    def test_connection(self) -> bool:
        """Issue a real query. Building the client alone validates nothing - the
        credential is lazy and a bad secret would still construct fine."""
        try:
            today = date.today()
            self._query_range(today - timedelta(days=1), today, granularity="Daily")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ queries
    @staticmethod
    def _column_index(columns, candidates) -> int | None:
        """Map by column NAME, never by position - Azure's column order is not
        contractual and has changed between API versions."""
        names = [(c.name or "").lower() for c in columns]
        for want in candidates:
            if want in names:
                return names.index(want)
        return None

    def _query_once(self, start: date, end: date, granularity: str, group: bool):
        from azure.mgmt.costmanagement.models import (
            QueryDefinition,
            QueryTimePeriod,
            QueryDataset,
            QueryAggregation,
            QueryGrouping,
        )

        dataset = QueryDataset(
            granularity=granularity,
            aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
        )
        if group:
            dataset.grouping = [QueryGrouping(type="Dimension", name="ServiceName")]

        query = QueryDefinition(
            type="ActualCost",
            timeframe="Custom",
            time_period=QueryTimePeriod(
                from_property=datetime.combine(start, datetime.min.time()),
                to=datetime.combine(end, datetime.min.time()),
            ),
            dataset=dataset,
        )
        return self._with_retry(
            lambda: self._get_client().query.usage(scope=self._scope(), parameters=query)
        )

    @staticmethod
    def _retry_after(exc, attempt: int) -> float:
        """Honour Azure's own backoff hint when it sends one."""
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        for name in _RETRY_AFTER_HEADERS:
            raw = headers.get(name)
            if raw:
                try:
                    return min(float(raw), 90.0)
                except (TypeError, ValueError):
                    pass
        return RETRY_BASE_SECONDS * (2 ** attempt)

    def _with_retry(self, call):
        last = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001 - re-raised below if not a 429
                if getattr(exc, "status_code", None) != 429:
                    raise
                last = exc
                if attempt == RETRY_ATTEMPTS - 1:
                    break
                time.sleep(self._retry_after(exc, attempt))
        raise last

    def _query_range(
        self, start: date, end: date, granularity: str = "Monthly", group: bool = False
    ) -> list[dict]:
        """Rows as {date, cost, service}, chunked to respect the 1-year cap.

        `end` is treated as exclusive to match the AWS provider's convention.
        """
        rows: list[dict] = []
        if end <= start:
            return rows

        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=MAX_SPAN_DAYS), end)
            result = self._query_once(cursor, chunk_end, granularity, group)
            rows.extend(self._decode(result))
            cursor = chunk_end

        return rows

    def _decode(self, result) -> list[dict]:
        columns = getattr(result, "columns", None) or []
        raw_rows = getattr(result, "rows", None) or []
        if not raw_rows:
            return []

        i_cost = self._column_index(columns, _COST_NAMES)
        i_date = self._column_index(columns, _DATE_NAMES)
        i_svc = self._column_index(columns, _SERVICE_NAMES)
        if i_cost is None:
            return []

        out = []
        for row in raw_rows:
            try:
                cost = float(row[i_cost])
            except (TypeError, ValueError, IndexError):
                continue
            out.append(
                {
                    "date": self._coerce_date(row[i_date]) if i_date is not None else None,
                    "cost": cost,
                    "service": row[i_svc] if i_svc is not None and i_svc < len(row) else "Unknown",
                }
            )
        return out

    @staticmethod
    def _coerce_date(value):
        """Azure returns YYYYMMDD as an int for Daily, YYYYMM-ish for Monthly, and
        occasionally an ISO string."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, int):
            s = str(value)
            if len(s) == 8:
                return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            if len(s) == 6:
                return date(int(s[:4]), int(s[4:6]), 1)
            return None
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    # ---------------------------------------------------------------- summaries
    def by_service(self, start: date, end: date) -> list[dict]:
        agg: dict[str, float] = {}
        for r in self._query_range(start, end, granularity="Monthly", group=True):
            name = r["service"] or "Unknown"
            agg[name] = agg.get(name, 0.0) + r["cost"]
        rows = [{"service": k, "usage": round(v, 2)} for k, v in agg.items() if v > 0.005]
        return sorted(rows, key=lambda r: -r["usage"])

    def monthly(self, start: date, end: date) -> list[dict]:
        agg: dict[str, float] = {}
        for r in self._query_range(start, end, granularity="Monthly"):
            if r["date"] is None:
                continue
            key = r["date"].strftime("%Y-%m")
            agg[key] = agg.get(key, 0.0) + r["cost"]
        return [
            {
                "month": month,
                "usage": round(total, 2),
                "credit_used": round(total, 2),  # derived, see module docstring
                "cash": 0.0,
                "other": {},
                "estimated": month == date.today().strftime("%Y-%m"),
            }
            for month, total in sorted(agg.items())
        ]

    # ----------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        cfg = self.config
        today = date.today()
        tomorrow = today + timedelta(days=1)  # end is exclusive

        granted = float(cfg["credits"]) if cfg.get("credits") is not None else None
        as_of = as_date(cfg["credits_as_of"]) if cfg.get("credits_as_of") else None

        notes = [
            "credits_used is DERIVED (cumulative ActualCost since credits_as_of); "
            "Azure has no credit record type to read a true drawdown from"
        ]

        # 11 months keeps the history window inside the 1-year custom-range cap
        # even before chunking, which keeps this to a single request.
        history_start = months_back(today, 11)
        months = self.monthly(history_start, tomorrow)

        if as_of is None:
            usage, rows_seen = 0.0, 0
            notes.append("no credits_as_of set, so nothing is being measured")
        elif as_of.day == 1 and as_of >= history_start:
            # Derivable from the history we already fetched - saves a query, and
            # Cost Management throttles per scope. Only exact on a month boundary.
            key = as_of.strftime("%Y-%m")
            hits = [m for m in months if m["month"] >= key]
            usage = sum(m["usage"] for m in hits)
            rows_seen = sum(1 for m in hits if m["usage"] > 0.005)
        else:
            window = self._query_range(as_of, tomorrow)
            usage = sum(r["cost"] for r in window)
            rows_seen = len(window)

        # An empty result set is NOT evidence of zero spend. Sponsorship offers
        # (MS-AZR-0036P) return HTTP 200 with no rows because their usage never
        # reaches Cost Management at all - so deriving "left = granted - 0" would
        # report the full grant as available when it may be nearly exhausted.
        # Refuse to produce a number rather than produce a confident wrong one.
        unverifiable = (
            granted is not None
            and as_of is not None
            and rows_seen == 0
            and (today - as_of).days > 31
        )
        if unverifiable:
            notes.append(
                f"NO usage records returned for {as_of} -> {today} despite a "
                f"${granted:,.0f} grant being configured. Cost Management returned "
                "200 with zero rows, which for a sponsorship offer means usage is "
                "not exposed to this API at all - it exists only at "
                "microsoftazuresponsorships.com. Refusing to report a balance"
            )

        if granted is None:
            notes.append(
                "no `credits` set - sponsorship balances are not exposed by any API, "
                "read the grant total from your Azure credits page and put it "
                "in config.yaml"
            )

        return {
            "status": "ok",
            "account_tail": self.account_tail(),
            "credits_granted": round(granted, 2) if granted is not None else None,
            "credits_used": None if unverifiable else round(usage, 2),
            "credits_remaining": (
                None
                if (unverifiable or granted is None)
                else round(granted - usage, 2)
            ),
            "credits_as_of": as_of.isoformat() if as_of else "-",
            "expires": as_date(cfg["expires"]).isoformat() if cfg.get("expires") else None,
            "usage_since_as_of": round(usage, 2),
            "cash_charged": None,  # indistinguishable from usage on Azure
            "by_service_90d": self.by_service(today - timedelta(days=90), tomorrow),
            "monthly": months,
            "warning": "; ".join(notes),
        }
