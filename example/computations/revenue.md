---
type: Attested Computation
title: Revenue for fiscal year
description: Recognized revenue for a fiscal year, per Finance's definition.
tags: [finance, revenue]
status: stable
runtime: bigquery
parameters:
  - {name: year, type: integer, required: true}
computation: references/computations/lib/revenue.sql
executor:
  resource: references/skills/run-on-bq.md
  receipt: [job_id, executed_sql, result]
attester:
  resource: references/attesters/revenue.py
verified:
  by: human:ahormati
  at: "2026-06-25T09:00:00Z"
stale_after: "2026-12-31"
sources:
  - id: rev-policy
    resource: https://wiki.acme/finance/revenue-recognition
    title: Revenue recognition policy
    author: team:finance-fpa
    last_modified: "2026-04-02"
---

# Computation

```
SELECT SUM(amount) AS revenue
FROM finance.recognized_revenue
WHERE fiscal_year = @year
```

Recognized revenue per the recognition policy.[^rev-policy]

\[^rev-policy\]: Revenue recognition policy
