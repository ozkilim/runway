"""GCP provider via BigQuery billing export.

Status: 🧪 wired but looking for testers — if you run this against a real GCP
account, please open an issue (working or not) so the status badge can be updated.

GCP has no cost API worth using directly; the supported path is the standard
billing export to BigQuery (docs/setup/gcp.md walks through enabling it). Two
consequences shape this provider:

1. The export does NOT backfill. Rows exist only from the day export was enabled,
   so `credits_as_of` must be on or after that day or drawdown will be undercounted.
   That is a silent-wrong-number hazard; snapshot() warns when the earliest row in
   the table is after credits_as_of.

2. Credits ARE first-class here (better than Azure): each row carries a `credits`
   array with negative amounts. `credits_used` is the abs sum of those — a true
   drawdown, same semantics as AWS's Credit record type. `cash` is cost + credits,
   i.e. what was actually charged.
"""

from datetime import date, timedelta

from .base import CloudProvider, as_date, months_back


class GCPProvider(CloudProvider):
    def __init__(self, config: dict):
        super().__init__("GCP", config)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                self.config["service_account_json"]
            )
            self._client = bigquery.Client(
                project=self.config["project_id"], credentials=creds
            )
        return self._client

    def _table(self) -> str:
        """Fully-qualified billing export table, e.g.
        `project.dataset.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`."""
        table = self.config["billing_table"]
        return table.strip("`")

    def account_tail(self) -> str:
        try:
            return self.config["project_id"][-4:]
        except Exception:
            return "????"

    def test_connection(self) -> bool:
        try:
            client = self._get_client()
            client.query(f"SELECT 1 FROM `{self._table()}` LIMIT 1").result()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ queries
    def _run(self, sql: str, params: list):
        from google.cloud.bigquery import QueryJobConfig

        job_config = QueryJobConfig(query_parameters=params)
        return list(self._get_client().query(sql, job_config=job_config).result())

    def _date_params(self, start: date, end: date):
        from google.cloud.bigquery import ScalarQueryParameter

        return [
            ScalarQueryParameter("start_date", "DATE", start.isoformat()),
            ScalarQueryParameter("end_date", "DATE", end.isoformat()),
        ]

    def _window(self, start: date, end: date) -> dict:
        """Cost, credit drawdown, and cash for [start, end). End exclusive to match
        the other providers."""
        sql = f"""
            SELECT
                SUM(cost) AS cost,
                SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credit
            FROM `{self._table()}`
            WHERE DATE(usage_start_time) >= @start_date
              AND DATE(usage_start_time) < @end_date
        """
        rows = self._run(sql, self._date_params(start, end))
        cost = float(rows[0].cost or 0) if rows else 0.0
        credit = float(rows[0].credit or 0) if rows else 0.0  # negative in export
        return {"usage": cost, "credit_used": abs(credit), "cash": cost + credit}

    def earliest_row(self) -> date | None:
        sql = f"SELECT MIN(DATE(usage_start_time)) AS d FROM `{self._table()}`"
        rows = self._run(sql, [])
        return rows[0].d if rows and rows[0].d else None

    def by_service(self, start: date, end: date) -> list[dict]:
        sql = f"""
            SELECT service.description AS service, SUM(cost) AS usage
            FROM `{self._table()}`
            WHERE DATE(usage_start_time) >= @start_date
              AND DATE(usage_start_time) < @end_date
            GROUP BY service
            HAVING usage > 0.005
            ORDER BY usage DESC
        """
        return [
            {"service": r.service, "usage": round(float(r.usage), 2)}
            for r in self._run(sql, self._date_params(start, end))
        ]

    def monthly(self, start: date, end: date) -> list[dict]:
        sql = f"""
            SELECT
                FORMAT_DATE('%Y-%m', DATE(usage_start_time)) AS month,
                SUM(cost) AS usage,
                SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credit
            FROM `{self._table()}`
            WHERE DATE(usage_start_time) >= @start_date
              AND DATE(usage_start_time) < @end_date
            GROUP BY month
            ORDER BY month
        """
        this_month = date.today().strftime("%Y-%m")
        out = []
        for r in self._run(sql, self._date_params(start, end)):
            usage = float(r.usage or 0)
            credit = abs(float(r.credit or 0))
            out.append(
                {
                    "month": r.month,
                    "usage": round(usage, 2),
                    "credit_used": round(credit, 2),
                    "cash": round(usage - credit, 2),
                    "other": {},
                    "estimated": r.month == this_month,
                }
            )
        return out

    # ----------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        cfg = self.config
        today = date.today()
        tomorrow = today + timedelta(days=1)

        as_of = as_date(cfg["credits_as_of"])
        granted = float(cfg["credits"])

        window = self._window(as_of, tomorrow)
        used = window["credit_used"]

        warning = None
        earliest = self.earliest_row()
        if earliest is None:
            warning = (
                "billing export table is empty - export only records usage from "
                "the day it was enabled onward (no backfill)"
            )
        elif earliest > as_of:
            warning = (
                f"billing export starts {earliest} but credits_as_of is {as_of}; "
                "drawdown before the export began cannot be counted, so "
                "credits_remaining is OVERSTATED"
            )

        return {
            "status": "ok",
            "account_tail": self.account_tail(),
            "credits_granted": round(granted, 2),
            "credits_used": round(used, 2),
            "credits_remaining": round(granted - used, 2),
            "credits_as_of": as_of.isoformat(),
            "expires": as_date(cfg["expires"]).isoformat() if cfg.get("expires") else None,
            "usage_since_as_of": round(window["usage"], 2),
            "cash_charged": round(window["cash"], 2),
            "by_service_90d": self.by_service(today - timedelta(days=90), tomorrow),
            "monthly": self.monthly(months_back(today, 12), tomorrow),
            "warning": warning,
        }
