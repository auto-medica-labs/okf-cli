---
type: "tables"
title: "Customers"
description: "One row per registered customer."
timestamp: "2026-07-10T10:58:34.555461+00:00"
---

## Schema

| Column      | Type      | Description                |
| ----------- | --------- | -------------------------- |
| customer_id | STRING    | Unique customer identifier |
| name        | STRING    | Customer display name      |
| email       | STRING    | Customer email address     |
| created_at  | TIMESTAMP | Account creation date      |

## Notes

Referenced by [orders](orders.md) via `customer_id`.
