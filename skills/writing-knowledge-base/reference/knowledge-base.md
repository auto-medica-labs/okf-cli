# Knowledge Base Reference

Knowledge base is plain Markdown organized as small, linked concepts.
Domain expert supplies facts. Agent supplies structure, questions, and editing.

## Basic concept

```markdown
# Customer Orders

> One row per completed customer order across all channels.

## Schema

| Column | Type | Description |
|--------|------|-------------|
| order_id | STRING | Unique order identifier |
| customer_id | STRING | Foreign key to customers |
| total_usd | NUMERIC | Order total in USD |

## Notes

Part of the [Sales Dataset](../datasets/sales.md).
```

## Source structure

```text
knowledge-base/
├── domain.md                    # Optional root-level domain overview
├── datasets/                    # Dataset concepts
│   └── sales.md
├── tables/                      # Table concepts
│   ├── customers.md
│   ├── orders.md
│   └── partitions/
│       └── daily.md
└── playbooks/                   # Operational procedure concepts
    ├── incident-response.md
    └── oncall-guide.md
```

Directory names become OKF concept types when bundled. For example,
`tables/orders.md` becomes a concept with type `tables` and ID
`tables/orders`.

## Writing rules

- Use one coherent concept per file.
- Start with `# Title`.
- Follow title with a concise `>` description.
- Put detail in the body.
- Link related concepts with relative Markdown links.
- Use lowercase, stable filenames.
- Do not add YAML frontmatter to source files; bundler generates it.

## Data concept checklist

Capture what asset contains, record grain, owner, consumers, schema, keys,
joins, partitions, freshness, quality limits, and caveats when known.

## Playbook checklist

Capture trigger, scope, ordered steps, decisions, expected outcomes, owners,
escalation, tools, and failure handling when known.
