# Data Freshness Incident

> Steps to triage a freshness alert on the orders pipeline.

## Trigger

A freshness alert fires when the [orders](/tables/orders.md) table lags more than 30 minutes behind its expected SLA.

## Steps

1. Check the ingestion job dashboard.
2. Verify upstream source connectivity.
3. Inspect the [Sales Dataset](/datasets/sales.md) for recent changes.
4. Notify the data engineering team if the issue persists.
