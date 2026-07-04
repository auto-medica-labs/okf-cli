# Daily Partition

> One partition per day for the orders table.

Part of the [orders](../../tables/orders.md) table's partitioning scheme.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| partition_date | DATE | The date of this partition |
| row_count | INT64 | Number of rows in the partition |
