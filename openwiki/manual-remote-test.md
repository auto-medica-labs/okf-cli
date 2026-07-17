# Manual remote publish/clone test

Step-by-step guide for testing `okf publish`, remote `list`/`show`, and `okf clone` against a local `okf-server`.

## 1. Install server extras

```bash
uv sync --all-extras
```

## 2. Start a local okf-server

Terminal 1:

```bash
uv run okf-server serve --host 0.0.0.0 --port 8080 --store ~/.okf/store --database ~/.okf/server.db
```

Default URL: `http://localhost:8080`.

## 3. Register a user and capture the token

Terminal 2:

```bash
curl -s -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret"}'
```

Save the returned `token` value:

```bash
export OKF_TOKEN="<token>"
export OKF_URL="http://localhost:8080"
```

## 4. Prepare and bundle local content

Use the repo example:

```bash
uv run okf bundle example --default-type reference --force
uv run okf validate example_knowledge_base
```

Or create a minimal bundle manually:

```bash
mkdir -p mybundle/tables
cat > mybundle/index.md <<'EOF'
# Contents
EOF
cat > mybundle/hello.md <<'EOF'
---
type: reference
---

# Hello
EOF
```

A manual bundle is already in OKF shape, so no separate bundling step is needed.

## 5. Publish the bundle

```bash
uv run okf publish example_knowledge_base mybundle --token "$OKF_TOKEN" --url "$OKF_URL"
```

Output prints the published URL, e.g. `http://localhost:8080/alice/mybundle`.

## 6. Read from the server

List concept IDs inside the remote bundle:

```bash
uv run okf list --remote alice/mybundle --url "$OKF_URL"
```

Show one concept:

```bash
uv run okf show --remote alice/mybundle --concept-id tables/customers --url "$OKF_URL"
```

## 7. Clone the published bundle

```bash
uv run okf clone alice/mybundle myclone --url "$OKF_URL"
```

## 8. Verify clone contents

```bash
ls myclone
uv run okf validate myclone
```

The cloned directory should contain the same concepts as the source bundle and pass conformance.

## Inspect what bundles a user owns

There is no CLI command for this yet; query the server directly.

Bundles owned by `alice`:

```bash
curl -s http://localhost:8080/alice | python3 -m json.tool
```

Entire server catalog:

```bash
curl -s http://localhost:8080/api/v1/catalog | python3 -m json.tool
```

Your own bundles when authenticated:

```bash
curl -s -H "Authorization: Bearer $OKF_TOKEN" \
  http://localhost:8080/api/v1/bundles | python3 -m json.tool
```

## Automated reference

`scripts/smoke.sh` builds the Docker image and exercises the full publish/list/show/clone cycle automatically:

```bash
bash scripts/smoke.sh
```
