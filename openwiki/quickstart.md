# okf-cli OpenWiki quickstart

`okf-cli` converts plain markdown directories into Open Knowledge Format (OKF) bundles, then validates and reads those bundles.

- CLI entrypoint: `src/okf/cli.py`
- Programmatic Python API: `src/okf/api.py`
- Shared parsing/conformance logic: `src/okf/core.py`
- Commands (thin wrappers): `src/okf/commands/bundle.py`, `src/okf/commands/validate.py`, `src/okf/commands/list.py`, `src/okf/commands/show.py`

## Start in 5 minutes

### CLI

```bash
uv sync
uv run okf --help
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
uv run okf list example_knowledge_base
uv run okf show example_knowledge_base tables/customers
uv run okf bundle example --default-type reference --force --strict-links
```

### Python API

```python
from okf.api import (
    bundle, convert_file, convert_content,
    list_concepts, show_concept, validate,
)

# Full directory bundle
result = bundle("example", "out", default_type="reference", force=True)
assert result.errors == []

# Single-file conversions
convert_file("example/tables/orders.md", "out/tables/orders.md", type_="tables")
convert_content("# Title\n\n> Desc\n\nBody.", "out/single.md", type_="reference")

concepts = list_concepts("out")
concept = show_concept("out", "tables/customers")
print(concept.body)

report = validate("out")
assert report.ok
```

Why this sequence:

1. `bundle` transforms raw markdown into OKF structure.
1. `validate` checks OKF conformance gate used by readers.
1. `list`/`show` operate only on conformant bundles.
1. `--strict-links` catches broken local `.md` references at bundle time.

## OpenWiki map

- [Architecture](architecture.md) — runtime shape, command wiring, extension points.
- [Workflows](workflows.md) — day-to-day CLI and contributor workflows.
- [Domain model](domain-model.md) — OKF concepts, frontmatter rules, reserved names, `.okfignore`.
- [Operations](operations.md) — setup, CI, release hygiene.
- [Testing](testing.md) — test suite map and change-focused test strategy.

## Where to start for common tasks

- Add/modify CLI behavior: start at [Architecture](architecture.md), then [Testing](testing.md).
- Change format/conformance rules: start at [Domain model](domain-model.md), then `src/okf/core.py` + validate/list/show tests.
- Update docs/user guidance: check `README.md` and align with this OpenWiki.
