---
name: writing-knowledge-base
description: Turn user provided content on any topic into a plain Markdown knowledge base. Invoked as /writing-knowledge-base with content to convert.
license: MIT
---

# Knowledge Base Construction

Convert the user's content directly into a structured Markdown knowledge base. Don't ask clarifying questions unless the content is genuinely unusable (e.g. empty or unintelligible) — infer structure, terminology, and grouping from what's given, and note any gaps inline rather than blocking on them.

## Workflow

1. Read the content and split it into coherent concepts (one idea per file — prefer several small linked files over one large one).
1. Create new directory with a name relative to the content user provide (e.g. `italian-food`, `turbocharge`, `formula-one`, etc. ).
1. Group concepts into type directories that fit the material's own structure. Let the content dictate the categories — e.g. `recipes/`, `policies/`, `species/`, `procedures/`, `terms/`, `people/`, `events/` — whatever natural groupings emerge. Don't force a data/tech taxonomy onto non-technical content.
1. Write each file using the format below, preserving the user's own terminology and facts. Never invent details, numbers, names, or steps that weren't given.
1. Add relative Markdown links between related concepts.
1. Save all files under an input directory your just created.

## Example file tree

```
cooking/
  recipes/
    italian/
      lasagna.md
      carbonara.md
    japanese/
      ramen.md
      sushi.md
  techniques/
    knife-skills.md
    emulsion.md
  ingredients/
    eggs.md
    flour-types.md
  faq.md
  common-mistake.md
```

- Root files (e.g. `faq.md`) are allowed
- File can be nested as deep as necessary and semantically sound.

## File format

```markdown
# Clear Concept Title

> One-sentence factual summary.

Body: context, details, steps, examples, caveats — whatever fits the concept.
```

- First line `# Title`, then a `>` description, then body detail.
- Use headings, lists, tables, or code blocks as they help retrieval — not all concepts need all of these.
- One concept per file. Directory name per type (e.g. `recipes/lasagna.md` → type `recipes`).
- Lowercase, stable filenames, no spaces.
- No `index.md`, `log.md`, `README.md` as concepts — bundler reserves these.
- No YAML frontmatter in source files

Do not fabricate any information on your own, use only what user provided to you.
