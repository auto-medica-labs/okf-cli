#!/usr/bin/env bash
set -euo pipefail

IMAGE="okf-server"
PORT="8123"
URL="http://localhost:${PORT}"
DATA_DIR="$(mktemp -d)"
BUNDLE_DIR="$(mktemp -d)"
CLONE_DIR="$(mktemp -d)"
CONTAINER_NAME="okf-smoke-$(date +%s)"

cleanup() {
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    rm -rf "${DATA_DIR}" "${BUNDLE_DIR}" "${CLONE_DIR}"
}
trap cleanup EXIT

# Build the server image.
echo "==> Building ${IMAGE} image"
docker build -t "${IMAGE}" -f Dockerfile .

# Create a tiny OKF bundle to publish.
echo "==> Preparing bundle"
mkdir -p "${BUNDLE_DIR}/tables"
cat > "${BUNDLE_DIR}/index.md" <<'EOF'
# Contents
EOF
cat > "${BUNDLE_DIR}/hello.md" <<'EOF'
---
type: reference
---

# Hello
EOF

# Run the server.
echo "==> Starting server container"
docker run --rm -d \
    --name "${CONTAINER_NAME}" \
    --user "$(id -u):$(id -g)" \
    -p "${PORT}:8080" \
    -v "${DATA_DIR}:/data" \
    "${IMAGE}"

# Wait for health endpoint.
echo "==> Waiting for server"
for _ in $(seq 1 30); do
    if curl -sf "${URL}/api/v1/" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Register a user and grab the token.
echo "==> Registering user"
TOKEN=$(curl -sf -X POST "${URL}/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d '{"username":"alice","password":"secret"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# Publish, list, show, clone.
echo "==> Publishing bundle"
OKF_URL="${URL}" uv run okf publish "${BUNDLE_DIR}" smoke --token "${TOKEN}"

echo "==> Listing remote concepts"
OKF_URL="${URL}" uv run okf list --remote alice/smoke

echo "==> Showing remote concept"
OKF_URL="${URL}" uv run okf show --remote alice/smoke --concept-id hello

echo "==> Cloning bundle"
OKF_URL="${URL}" uv run okf clone alice/smoke "${CLONE_DIR}"

# Verify clone contents.
echo "==> Verifying clone"
if [[ ! -f "${CLONE_DIR}/hello.md" ]]; then
    echo "ERROR: cloned hello.md not found"
    exit 1
fi

echo "==> Smoke test passed"
