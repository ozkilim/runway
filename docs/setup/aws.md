# AWS setup (~5 minutes)

Status: ✅ battle-tested. This is the reference provider.

You'll create a read-only IAM user that can see billing data and nothing else,
enable Cost Explorer, and read your credit grant off the console once.

> **Tip:** you can hand this whole file to your coding agent and say "walk me
> through this" — everything below is copy-pasteable.

## 1. Enable Cost Explorer (one-time, free to enable)

1. Sign in to the AWS console → **Billing and Cost Management** → **Cost Explorer**.
2. If you see a "Launch Cost Explorer" / enable prompt, click it.
3. First-time enablement backfills for up to **24 hours**. If runway later reports
   `DataUnavailableException`, this is why — just wait.

Note: the Cost Explorer **API** costs $0.01 per request. A full runway table is a
handful of requests, so roughly $0.05/run. (You'll see it show up in its own
output as "Cost Explorer". Yes, really.)

## 2. Allow IAM users to see billing (one-time, needs root/admin)

By default only the root user can see billing data.

1. Sign in as the **root user** → click your account name (top right) → **Account**.
2. Scroll to **IAM user and role access to billing information** → **Edit** →
   check **Activate IAM Access** → **Update**.

If you skip this, runway will report `AccessDeniedException` even with a correct
IAM policy.

## 3. Create a minimal IAM user

1. Console → **IAM** → **Users** → **Create user**. Name it e.g. `runway-readonly`.
   No console access needed.
2. **Attach policies directly** → **Create policy** → JSON tab → paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RunwayCostRead",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

3. Name the policy `runway-cost-read`, create it, attach it to the user, finish
   creating the user.
4. Open the user → **Security credentials** → **Create access key** →
   use case "Application running outside AWS" → copy the **Access key ID** and
   **Secret access key**.

That's the entire blast radius: this key can read cost aggregates and its own
identity. It cannot see resources, data, or spend money.

## 4. Read your credit grant off the console (one-time)

1. Console → **Billing and Cost Management** → **Credits**.
2. Note three things:
   - **Remaining balance** (this becomes `credits`)
   - **Today's date** (this becomes `credits_as_of`)
   - **Expiration date** (this becomes `expires`)

No cloud exposes remaining credit via API — this one manual read is what makes the
math work. **`credits_as_of` is load-bearing**: runway computes
`remaining = credits − drawdown since credits_as_of`. If the console said $10,000
remaining *today*, then `credits_as_of` is *today* — not the day the grant started.
Measuring from the wrong date silently produces a wrong balance.

No credits? Set `credits` to your budget cap (or leave it and read the `used`
column only) — the spend tracking works regardless.

## 5. Fill in the config

Edit `~/.runway/config.yaml`:

```yaml
aws:
  enabled: true
  access_key_id: "AKIA..."
  secret_access_key: "..."
  region: "us-east-1"        # Cost Explorer is global; region rarely matters
  credits: 10000             # from step 4
  credits_as_of: 2026-01-15  # from step 4
  expires: 2027-12-31        # from step 4
```

## 6. Verify

```bash
.venv/bin/python runway.py --check
```

Expect `aws    OK account ...1234`. Then run it for real:

```bash
.venv/bin/python runway.py
```

## Troubleshooting

| Error | Fix |
|---|---|
| `AccessDeniedException` | Step 2 (IAM billing access switch) or the policy in step 3 |
| `DataUnavailableException` | Cost Explorer still backfilling (step 1) — wait up to 24h |
| `InvalidClientTokenId` | Access key id is wrong |
| `SignatureDoesNotMatch` | Secret key wrong — check for stray whitespace from the copy |
| Numbers look too low | `credits_as_of` more than ~13 months ago exceeds Cost Explorer retention; runway warns about this |
| Table shows $0.00 everywhere | You're credit-funded and something queried the unfiltered total (Usage and Credit cancel). runway itself filters by record type — if you're extending the provider, keep doing that |
