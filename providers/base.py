"""The provider contract. Implement this to add a cloud — see CONTRIBUTING.md.

A provider turns credentials + a manually-entered credit grant into a snapshot of
facts. It must emit facts only: no forecasting, no thresholds, no verdicts. If a
number cannot be measured honestly, return None for it and explain why in
`warning` — a None renders as UNKNOWN, which is infinitely better than a
confident wrong figure.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime


def as_date(value) -> date:
    """PyYAML parses unquoted YYYY-MM-DD into a date already; accept either form."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def months_back(d: date, n: int) -> date:
    y, m = d.year, d.month - n
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


class CloudProvider(ABC):
    """Abstract base class for cloud cost providers.

    Config keys every provider shares (all set by the user in ~/.runway/config.yaml):
      credits        float  — total credit grant, read off the provider's console
      credits_as_of  date   — the date that grant figure was true (LOAD-BEARING:
                              remaining = credits − drawdown since this date)
      expires        date   — when the credits expire
    plus whatever credentials that cloud needs.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def test_connection(self) -> bool:
        """Cheap real API call proving the credentials work. Must not raise."""

    @abstractmethod
    def snapshot(self) -> dict:
        """The full fact payload for this provider. Required keys:

        status              "ok" (errors are handled by the caller — just raise)
        account_tail        last 4 chars of the account/subscription/project id
        credits_granted     float | None
        credits_used        float | None  (None = could not measure; renders UNKNOWN)
        credits_remaining   float | None
        credits_as_of       ISO date str
        expires             ISO date str | None
        usage_since_as_of   float
        cash_charged        float | None  (real money beyond credits; None = unknown)
        by_service_90d      [{service, usage}] sorted desc
        monthly             [{month, usage, credit_used, cash, other, estimated}]
        warning             str | None    (anything the reader must know to trust
                                           or distrust the numbers above)
        """

    def account_tail(self) -> str:
        return "????"
