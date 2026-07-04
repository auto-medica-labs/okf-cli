# Customers

> One row per registered customer.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| customer_id | STRING | Unique customer identifier |
| name | STRING | Customer display name |
| email | STRING | Customer email address |
| created_at | TIMESTAMP | Account creation date |

## Notes

Referenced by [orders](/tables/orders.md) via `customer_id`.
