# Azure setup (~10 minutes)

Status: ⚠️ works for **pay-as-you-go / Enterprise Agreement** subscriptions.
**Blind for sponsorship offers** — read the box below before doing anything.

> ### ⚠️ Sponsorship accounts (MS-AZR-0036P and friends)
> If your credits came from Microsoft for Startups / Azure Sponsorships, stop:
> **your usage never reaches the Cost Management API at all.** The API returns
> HTTP 200 with zero rows, and your true balance lives only at
> [microsoftazuresponsorships.com](https://www.microsoftazuresponsorships.com).
> runway detects this and refuses to report a balance rather than tell you the
> full grant is still available when it isn't.
>
> If you know a working API path for sponsorship balances, that's the single most
> wanted contribution in this repo — open an issue!

## 1. Create a service principal (app registration)

1. Azure portal → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name it `runway-readonly`, leave defaults, **Register**.
3. From the Overview page copy:
   - **Application (client) ID** → `client_id`
   - **Directory (tenant) ID** → `tenant_id`
4. **Certificates & secrets** → **New client secret** → copy the secret **Value**
   (not the Secret ID) immediately — it's shown once → `client_secret`.

## 2. Grant it read access to costs

1. Portal → **Subscriptions** → pick your subscription → copy the
   **Subscription ID** → `subscription_id`.
2. On that subscription: **Access control (IAM)** → **Add role assignment** →
   role **Cost Management Reader** → assign to your `runway-readonly` app.

That's the whole blast radius: cost aggregates, read-only.

## 3. Read your credit grant (one-time, manual)

Portal → **Cost Management + Billing** → **Credits + Commitments** (path varies by
offer type). Note the remaining balance (`credits`), today's date
(`credits_as_of`), and the expiry (`expires`). Sponsorship users: this page is
empty for you — the numbers are only at microsoftazuresponsorships.com.

## 4. Install the Azure SDK and fill in the config

The Azure SDK is not installed by default. In the repo:

```bash
.venv/bin/pip install azure-identity azure-mgmt-costmanagement
```

Edit `~/.runway/config.yaml`:

```yaml
azure:
  enabled: true
  tenant_id: "..."
  client_id: "..."
  client_secret: "..."
  subscription_id: "..."
  credits: 5000
  credits_as_of: 2026-01-15
  expires: 2026-12-31
```

## 5. Verify

```bash
.venv/bin/python runway.py --check
.venv/bin/python runway.py --provider azure
```

## Honesty notes (why Azure numbers read differently)

- Azure has **no credit record type**. `used` is *derived* — cumulative ActualCost
  since `credits_as_of` — not read from credit records like AWS. The output says so.
- `cash` is shown as `-`: on Azure, real-money charges are indistinguishable from
  credit-covered usage in this API.
- Cost Management throttles hard (HTTP 429). runway retries with the server's own
  backoff hints; a slow run is normal.
