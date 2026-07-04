# OKF Example

This directory contains plain markdown files written by domain experts.
Run `okf bundle` to convert them into an OKF-conformant knowledge bundle.

```bash
# From repo root:
uv run okf bundle example output-bundle

# With a default type for root-level files (if any):
uv run okf bundle example output-bundle --default-type reference
```
