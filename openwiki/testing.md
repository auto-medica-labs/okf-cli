# Testing

## Test suite map

- Core unit tests: `tests/test_core.py`
  - parsing helpers (`parse_md`, `parse_frontmatter`)
  - frontmatter generation (`build_frontmatter`)
  - conformance engine (`check_conformance`)
- CLI integration tests:
  - bundling: `tests/cli/test_bundle.py`
  - list: `tests/cli/test_list.py`
  - show: `tests/cli/test_show.py`
  - validate: `tests/cli/test_validate.py`

## Run tests

```bash
uv run pytest -q
```

## Change-oriented guidance

### If editing `src/okf/core.py`

Run at minimum:

```bash
uv run pytest -q tests/test_core.py tests/cli/test_validate.py tests/cli/test_list.py tests/cli/test_show.py
```

Reason: conformance and parsing affect all reader commands.

### If editing `src/okf/commands/bundle.py`

Run at minimum:

```bash
uv run pytest -q tests/cli/test_bundle.py tests/test_core.py
```

Reason: bundler behavior depends on parser/frontmatter helpers.

### If editing CLI registration or command args (`src/okf/cli.py`, command signatures)

Run full CLI coverage:

```bash
uv run pytest -q tests/cli
```

## Behaviors with dedicated regression coverage

- `.okfignore` parsing and skip semantics, including non-UTF-8 failure.
- Lenient parsing fallback when strict markdown format is missing.
- Reserved filename differences between bundling and spec conformance.
- Root `index.md` special allowance for `okf_version` only.
- `list`/`show` hard failure on non-conformant bundles.
- `show` path traversal guard.
- Link checking: `_resolve_md_target` path resolution, `--strict-links` fatal mode, missing/out-of-bundle targets.

Primary evidence: `tests/cli/*.py`, `tests/test_core.py`.
