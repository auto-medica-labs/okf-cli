# Customer Orders

> One row per completed customer order across all channels.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| order_id | STRING | Unique order identifier |
| customer_id | STRING | Foreign key to customers |
| total_usd | NUMERIC | Order total in USD |
| placed_at | TIMESTAMP | When the order was placed |

## Notes

Part of the [Sales Dataset](../datasets/sales.md). Joined with [customers](customers.md) on `customer_id`.
