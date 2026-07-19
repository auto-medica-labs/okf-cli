# Plan: Browse UI for okf-server

## Motivation

Server currently serves raw markdown and JSON to browsers. Visiting
`okf.com/alice/widgets` shows `# Welcome` as plain text — not browsable
or shareable as a web page.

Goal: make any published OKF bundle readable in a browser with minimal
UI, so knowledge can be shared and consumed freely without the CLI.

## Constraints

- CLI commands (`okf list --remote`, `okf show --remote`, `okf clone`)
  use `/{username}/{bundle}/concepts`, `/{username}/{bundle}/concepts/{cid}`,
  and `/{username}/{bundle}/archive`. These must stay raw (JSON/markdown/gzip).
- No breaking changes to the API routes.
- Zero JS. No framework. No build step.
- One new dependency: `markdown` (Python). `jinja2` is already a usable
  Starlette integration — add explicitly to pyproject.toml.

## Route changes

| Route | Before | After |
|---|---|---|
| `GET /` | 404 | HTML catalog (all users/bundles) |
| `GET /{username}` | `["widgets"]` JSON | HTML user page with bundle links |
| `GET /{username}/{bundle}` | raw index.md | HTML: rendered index + concept list |
| `GET /api/v1/users/{username}/bundles` | — | NEW: JSON list of user's bundles (API parity) |
| All other routes | unchanged | unchanged |

## Templates

```
src/okf/server/templates/
├── base.html        # HTML shell, nav, minimal CSS
├── catalog.html     # / — user/bundle grid
├── user.html        # /{username} — bundle links
├── bundle.html      # /{username}/{bundle} — rendered index.md + concept sidebar
└── concept.html     # (optional) standalone rendered concept page
```

Templates render server-side with Jinja2. One `<style>` block in base.html,
no external CSS. Dark/light mode via `prefers-color-scheme`.

## What's NOT in scope

- Login/register UI — keep API-only
- JS interactivity, search, pagination
- Concept graph, tags, metadata display beyond frontmatter
- CSS framework or design system
- Changes to CLI commands or client library (`remote.py`)

## Files changed

```
pyproject.toml                          # +markdown, +jinja2 to server extras
src/okf/server/app.py                   # +HTML routes, +Jinja2Templates
src/okf/server/templates/base.html      # new
src/okf/server/templates/catalog.html   # new
src/okf/server/templates/user.html      # new
src/okf/server/templates/bundle.html    # new
tests/server/test_server_api.py         # update user/bundle tests, add HTML route tests
```

## Test strategy

- Update `test_user_bundles` — expect HTML instead of JSON
- Update `test_bundle_landing` — expect HTML instead of raw markdown
- Add test for `GET /` catalog HTML page
- Add test for `GET /api/v1/users/{username}/bundles` JSON endpoint
- Add test for concept HTML rendering
