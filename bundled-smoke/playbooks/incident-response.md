---
type: "playbooks"
title: "Data Freshness Incident"
description: "Steps to triage a freshness alert on the orders pipeline."
timestamp: "2026-07-10T10:58:34.555461+00:00"
---

## Trigger

A freshness alert fires when the [orders](../tables/orders.md) table lags more than 30 minutes behind its expected SLA.

## Steps

1. Check the ingestion job dashboard.
1. Verify upstream source connectivity.
1. Inspect the [Sales Dataset](../datasets/sales.md) for recent changes.
1. Notify the data engineering team if the issue persists.
