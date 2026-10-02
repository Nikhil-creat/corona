#!/usr/bin/env bash
set -euo pipefail
API=${API_URL:-http://localhost:8000}
curl -fsS "$API/healthz" && echo
curl -fsS "$API/readyz" && echo
curl -fsS "$API/metrics" | head -n 5
