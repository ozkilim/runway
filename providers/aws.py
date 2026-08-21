"""AWS Cost Explorer provider. The reference implementation — battle-tested.

The one thing to understand: Cost Explorer returns the SUM of all record types when
unfiltered. Under credit funding, Usage and Credit cancel exactly and the total
reads $0.00. Every figure below is therefore explicit about which record type it
means: `credits_used` reads the Credit records directly (true drawdown), `usage`
reads Usage records (gross consumption), and `cash` is the net of everything —
which is exactly the real money charged beyond credits.
"""

from datetime import date, timedelta

from .base import CloudProvider, as_date, months_back

USAGE_ONLY = {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Usage"]}}
CREDIT_ONLY = {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit"]}}


class AWSProvider(CloudProvider):
    def __init__(self, config: dict):
        super().__init__("AWS", config)
        self._client = None

    # ------------------------------------------------------------------ clients
    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "ce",
                aws_access_key_id=self.config["access_key_id"],
                aws_secret_access_key=self.config["secret_access_key"],
                region_name=self.config.get("region", "us-east-1"),
            )
        return self._client

    def _sts(self):
        import boto3

        return boto3.client(
            "sts",
            aws_access_key_id=self.config["access_key_id"],
            aws_secret_access_key=self.config["secret_access_key"],
            region_name=self.config.get("region", "us-east-1"),
        )

    def account_tail(self) -> str:
        try:
            return self._sts().get_caller_identity()["Account"][-4:]
        except Exception:
            return "????"

    def test_connection(self) -> bool:
        try:
            today = date.today()
            self._get_client().get_cost_and_usage(
                TimePeriod={
                    "Start": (today - timedelta(days=1)).isoformat(),
                    "End": today.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ queries
    def _query(self, start: date, end: date, group_by=None, cost_filter=None,
               granularity="MONTHLY"):
        kwargs = {
            "TimePeriod": {"Start": start.isoformat(), "End": end.isoformat()},
            "Granularity": granularity,
            "Metrics": ["UnblendedCost"],
        }
        if group_by:
            kwargs["GroupBy"] = [{"Type": "DIMENSION", "Key": group_by}]
        if cost_filter:
            kwargs["Filter"] = cost_filter
        return self._get_client().get_cost_and_usage(**kwargs)

    def _total(self, start: date, end: date, cost_filter=None) -> float:
        """Sum a metric across every time bucket. End is exclusive in Cost Explorer."""
        resp = self._query(start, end, cost_filter=cost_filter)
        return sum(
            float(b["Total"]["UnblendedCost"]["Amount"])
            for b in resp.get("ResultsByTime", [])
        )

    def by_service(self, start: date, end: date) -> list[dict]:
        """Gross usage per service. Aggregated across buckets: a window spanning two
        calendar months returns one bucket per month, each with its own groups."""
        resp = self._query(start, end, group_by="SERVICE", cost_filter=USAGE_ONLY)
        agg: dict[str, float] = {}
        for bucket in resp.get("ResultsByTime", []):
            for g in bucket.get("Groups", []):
                name = g["Keys"][0]
                agg[name] = agg.get(name, 0.0) + float(
                    g["Metrics"]["UnblendedCost"]["Amount"]
                )
        rows = [{"service": k, "usage": round(v, 2)} for k, v in agg.items() if v > 0.005]
        return sorted(rows, key=lambda r: -r["usage"])

    def monthly(self, start: date, end: date) -> list[dict]:
        """Per-month usage / credit / cash. Record types beyond Usage and Credit
        (Refund, Tax, ...) are retained under `other` rather than silently dropped."""
        resp = self._query(start, end, group_by="RECORD_TYPE")
        out = []
        for bucket in resp.get("ResultsByTime", []):
            kinds = {
                g["Keys"][0]: float(g["Metrics"]["UnblendedCost"]["Amount"])
                for g in bucket.get("Groups", [])
            }
            usage = kinds.get("Usage", 0.0)
            credit = abs(kinds.get("Credit", 0.0))
            other = {
                k: round(v, 2)
                for k, v in kinds.items()
                if k not in ("Usage", "Credit") and abs(v) > 0.005
            }
            out.append(
                {
                    "month": bucket["TimePeriod"]["Start"][:7],
                    "usage": round(usage, 2),
                    "credit_used": round(credit, 2),
                    "cash": round(sum(kinds.values()), 2),
                    "other": other,
                    "estimated": bucket.get("Estimated", False),
                }
            )
        return out

    # ------------------------------------------------------------------ snapshot
    def snapshot(self) -> dict:
        """The full fact payload for this provider. No forecasting, no thresholds."""
        cfg = self.config
        today = date.today()
        tomorrow = today + timedelta(days=1)  # End is exclusive

        as_of = as_date(cfg["credits_as_of"])
        granted = float(cfg["credits"])

        used = abs(self._total(as_of, tomorrow, CREDIT_ONLY))
        usage = self._total(as_of, tomorrow, USAGE_ONLY)
        cash = self._total(as_of, tomorrow)  # net of all record types

        history_start = months_back(today, 12)
        retention_warning = None
        if as_of < months_back(today, 13):
            retention_warning = (
                f"credits_as_of ({as_of}) predates Cost Explorer retention "
                "(~13 months); usage before that window cannot be counted"
            )

        return {
            "status": "ok",
            "account_tail": self.account_tail(),
            "credits_granted": round(granted, 2),
            "credits_used": round(used, 2),
            "credits_remaining": round(granted - used, 2),
            "credits_as_of": as_of.isoformat(),
            "expires": as_date(cfg["expires"]).isoformat() if cfg.get("expires") else None,
            "usage_since_as_of": round(usage, 2),
            "cash_charged": round(cash, 2),
            "by_service_90d": self.by_service(today - timedelta(days=90), tomorrow),
            "monthly": self.monthly(history_start, tomorrow),
            "warning": retention_warning,
        }
