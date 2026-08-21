# GCP setup (~15 minutes, then wait a day)

Status: 🧪 wired but looking for testers. If you run this against a real account,
please open an issue saying whether it worked — that's a valuable contribution by
itself.

GCP has no usable cost API; the supported path is the standard **billing export to
BigQuery**. Two consequences:

> ### ⚠️ The export does NOT backfill
> Rows exist only from the day you enable the export. Enable it **today** even if
> you don't finish the rest of the setup — every day you wait is a day of spend
> runway can never see. And set `credits_as_of` to a date **on or after** the day
> the export started, or your balance will be silently overstated (runway warns
> when it detects this).

The good news: unlike Azure, GCP's export has **first-class credit records**, so
once running, drawdown is measured truly (like AWS), not derived.

## 1. Enable the billing export (do this first)

1. Console → **Billing** → **Billing export** → **BigQuery export** →
   **Standard usage cost** → **Edit settings**.
2. Pick/create a project and create a dataset, e.g. `billing_export`.
3. Save. The table appears within a few hours, named like
   `gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`.
4. Copy the full table id: `your-project.billing_export.gcp_billing_export_v1_...`
   → `billing_table`.

## 2. Create a read-only service account

1. Console → **IAM & Admin** → **Service Accounts** → **Create service account**,
   name `runway-readonly`.
2. Grant roles on the project holding the dataset:
   - **BigQuery Job User** (run queries)
   - **BigQuery Data Viewer** (read the export dataset — you can scope this to the
     dataset only via the dataset's Sharing settings for least privilege)
3. **Keys** → **Add key** → JSON → download. Store it outside any git repo, e.g.
   `~/.runway/gcp-service-account.json`, and `chmod 600` it.

## 3. Read your credit grant (one-time, manual)

Console → **Billing** → **Credits**. Note remaining balance (`credits`), today's
date (`credits_as_of` — but not earlier than the export start!), expiry (`expires`).

## 4. Install the SDK and fill in the config

```bash
.venv/bin/pip install google-cloud-bigquery
```

Edit `~/.runway/config.yaml`:

```yaml
gcp:
  enabled: true
  service_account_json: "/home/you/.runway/gcp-service-account.json"
  project_id: "your-gcp-project-id"
  billing_table: "your-project.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX"
  credits: 3000
  credits_as_of: 2026-01-15
  expires: 2026-12-31
```

## 5. Verify

```bash
.venv/bin/python runway.py --check
.venv/bin/python runway.py --provider gcp
```

## Costs

BigQuery queries against a billing export are typically pennies (the table is
small and queries scan little). The export itself is free; standard BigQuery
storage rates apply (near zero for this data volume).
