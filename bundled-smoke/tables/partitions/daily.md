---
type: "partitions"
title: "Daily Partition"
description: "One partition per day for the orders table."
timestamp: "2026-07-10T10:58:34.559461+00:00"
---

Part of the [orders](../../tables/orders.md) table's partitioning scheme.

## Schema

| Column         | Type  | Description                     |
| -------------- | ----- | ------------------------------- |
| partition_date | DATE  | The date of this partition      |
| row_count      | INT64 | Number of rows in the partition |
