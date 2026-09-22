# Run on BigQuery

Execute a SQL query against BigQuery and return a receipt.

## Parameters

- `query`: The SQL to execute
- `project`: BigQuery project ID

## Receipt

Returns `{job_id, executed_sql, result}` where `result` is the query output as a JSON array of rows.
