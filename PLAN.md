# Plan: Merge pre-existing frontmatter in `okf bundle`

## Goal
Let knowledge-base authors put OKF frontmatter directly in their source markdown before running `okf bundle`. The bundler should detect, parse, and merge those fields instead of overwriting them.

## Current state
- `okf bundle` treats input as plain markdown.
- `parse_md()` extracts `# Title`, `> description`, and body.
- Any existing YAML frontmatter is ignored and ends up in the body.
- `_write_concept()` generates only `type`, `title`, `description`, and `generated`.

## Desired behavior
1. Detect YAML frontmatter at the start of input markdown.
2. Preserve producer-defined fields such as `tags`, `resource`, `sources`, `verified`, `status`, `stale_after`, and Attested Computation fields.
3. Auto-generate `type`, `title`, `description`, and `generated` only when absent or as specified below.
4. Strip the input frontmatter from the body so it is not duplicated in output.

## Field conflict resolution

| Field | Source of truth | Rationale |
|-------|-----------------|-----------|
| `type` | CLI `--default-type` | Bundler categorizes the concept. |
| `generated` | Bundler | Records that `okf-cli` produced this concept wrapper. |
| `title` | Input frontmatter > parsed title | Author-set value wins. |
| `description` | Input frontmatter > parsed description | Author-set value wins. |
| All other fields (`tags`, `resource`, `sources`, `verified`, `status`, `stale_after`, `runtime`, `parameters`, `computation`, `executor`, `attester`) | Input frontmatter | Bundler cannot infer these. |

## Key design decisions

- **`generated` is always overwritten.** Upstream provenance should live in `sources`.
- **`type` is always set from the CLI.** An input `type` is ignored.
- **Malformed frontmatter in `--strict` fails.** In normal mode, treat it as plain markdown.
- **`okf_version` in non-root input files is ignored.** It only belongs in the bundle-root `index.md`.
- **Root `index.md` generation is unchanged.** It still gets `okf_version: "0.2"` from the bundler.

## Implementation steps

1. **Extend frontmatter parsing**
   - Add `parse_md_with_frontmatter()` in `src/okf/core.py`.
   - Reuse existing `parse_frontmatter()` logic (detect `---` at line 0, parse with `yaml.safe_load`).
   - Return `(frontmatter_dict, title, description, body)`.
   - Fall back to current `parse_md()` behavior when there is no frontmatter or it is malformed.

2. **Update frontmatter rendering**
   - Change `build_frontmatter()` in `src/okf/core.py` to accept an optional `extras: dict[str, Any]`.
   - Build a complete dict and render with `yaml.safe_dump(..., sort_keys=False)` for valid, predictable YAML.

3. **Update concept writing**
   - Change `_write_concept()` in `src/okf/api.py` to accept existing frontmatter.
   - Merge fields per the conflict table above.
   - Write the merged frontmatter plus the stripped body.

4. **Update conversion entry points**
   - Update `convert_file()` and `bundle()` in `src/okf/api.py` to use `parse_md_with_frontmatter()` and pass existing frontmatter to `_write_concept()`.

5. **Add tests**
   - Preserve simple fields: `tags`, `resource`.
   - Preserve trust/provenance/lifecycle fields: `sources`, `verified`, `status`, `stale_after`.
   - Preserve Attested Computation fields: `runtime`, `parameters`, `computation`, `executor`, `attester`.
   - Frontmatter `title`/`description` override parsed body values.
   - CLI `type` overrides input frontmatter `type`.
   - `generated` is always overwritten by the bundler actor.
   - Malformed frontmatter is handled correctly in normal and `--strict` modes.

## Dependencies

No new dependencies. `pyyaml` is already used in `src/okf/core.py`:

```python
import yaml
result = yaml.safe_load(content)
```

## First slice

Implement preservation of `tags`, `resource`, and any unknown keys, plus frontmatter `title`/`description` precedence. Attestation fields will work automatically because they are unknown keys to the bundler.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `---` elsewhere in file mistaken for frontmatter | Only treat `---` at the very start of the file as frontmatter. |
| Nested YAML values break manual rendering | Use `yaml.safe_dump` for the merged frontmatter dict. |
| Users surprised that `generated` is overwritten | Document the behavior; it matches the spec. |
| Round-trip instability | Test output through `parse_frontmatter()` and keep deterministic field order. |
