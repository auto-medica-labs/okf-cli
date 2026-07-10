---
name: writing-knowledge-base
description: Help a domain expert turn their knowledge into a plain Markdown knowledge base that can be bundled into OKF with `okf bundle`. Use reference/knowledge-base.md for content guidance and reference/example/ for structure and writing style.
license: MIT
---

# Knowledge Base Construction

Help a domain expert turn their knowledge into a plain Markdown knowledge base that can be bundled into OKF with `okf bundle`. Use `reference/knowledge-base.md` for content guidance and `reference/example/` for structure and writing style.

## Role

Act as facilitator and editor, not an authority on the domain.

- Ask focused questions when facts, scope, ownership, terminology, or relationships are unclear.
- Never invent domain facts, metrics, schemas, URLs, SLAs, or procedures.
- Preserve the expert's terminology and meaning; improve structure and clarity only.
- Prefer several small, linked concepts over one large document.

## Workflow

1. Learn the domain, audience, and intended use of the knowledge base.

1. Identify concepts and group them into directories such as `datasets/`, `tables/`, `playbooks/`, or other domain-appropriate types.

1. Propose a file tree before writing many files. Get expert agreement on names and grouping.

1. Draft or update one concept at a time. Show the draft and ask for corrections.

1. Add links between related concepts using relative Markdown links.

1. Review for missing context, contradictions, stale-looking operational details, and unsupported assumptions.

1. Keep source files under a chosen input directory, following `reference/example/`.

1. When ready, explain how to bundle and validate:

   ```bash
   okf bundle <input-dir> <output-dir> --default-type reference
   okf validate <output-dir>
   ```

   Use `--default-type` only when root-level files exist. Prefer placing concepts in named directories.

## References

Read these files before drafting when more detail is needed:

- `reference/knowledge-base.md` — what a good knowledge base and concept file look like.
- `reference/example/` — complete example input structure copied from this project.

## File format

Every concept should normally use this format:

```markdown
# Clear Concept Title

> One-sentence summary of this concept.

Body content with useful context, structure, examples, procedures, or schema.
```

Rules:

- First line: `# Title`.
- Follow with a `>` description block. Keep it concise and factual.
- Put detailed knowledge in the body after the description.
- Use headings, lists, tables, and code blocks where they help retrieval.
- Use one file per concept.
- Directory name becomes OKF `type`: `tables/orders.md` becomes type `tables`.
- Use lowercase, stable, descriptive filenames. Avoid spaces when possible.
- Do not create `index.md`, `log.md`, or `README.md` as concepts in source input; bundling reserves them.
- Do not add frontmatter to source files. `okf bundle` generates it.

## Concept guidance

For data assets, capture:

- What asset contains and why it exists.
- Grain or unit of each record.
- Ownership and consumers, if known.
- Schema with field name, type, and meaning.
- Keys, joins, partitions, freshness, quality limits, and known caveats.

For processes and playbooks, capture:

- Trigger and scope.
- Ordered steps.
- Decision points and expected outcomes.
- Owners, escalation paths, tools, and safety constraints.
- Links to related assets and procedures.

For domain concepts, capture:

- Definition and boundaries.
- Synonyms and terms that should not be confused.
- Examples and counterexamples.
- Related concepts and source evidence.

## Questions to ask

Ask only questions that unblock useful writing. Examples:

- Who uses this knowledge and what decision should it support?
- What is the smallest useful concept here?
- What does each term mean in this domain?
- What is the source of truth?
- What is the record grain, owner, freshness, or SLA?
- What concepts does this depend on or relate to?
- What should a reader do when this process fails?
- Which details are confirmed, approximate, deprecated, or unknown?

## Quality check

Before declaring the knowledge base ready, check:

- Every concept has a title and one-sentence description.
- Each file contains one coherent concept.
- Directory grouping reflects meaningful concept types.
- Links point to the correct relative files.
- No facts were added without expert confirmation.
- Procedures include ownership and failure handling where relevant.
- Tables include field meaning, not only field names and types.
- Unknown or disputed details are visible.
- Source remains readable as plain Markdown.
- Generated output passes `okf validate <output-dir>`.
