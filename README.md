# Corona — Self-Healing Spatial Digital Twin

Live demo (after you enable GitHub Pages): `https://<your-username>.github.io/<repo-name>/`

| Path | What it is |
|---|---|
| `index.html` | **The GitHub Pages site.** Single-file 3D digital twin (three.js) with an in-browser self-healing agent swarm: Validator → Compliance-RAG → Risk → Planner ⇄ Verifier → signed human approval → Executor. Includes copilot commands, predictive failure forecast, federated-model counter. All data is simulated in your browser. |
| `platform/` | **The full production stack** (Next.js 15 + R3F, FastAPI, LangGraph, Neo4j + pgvector, Redpanda, Redis, ViT/CNN, post-quantum crypto, Docker/Helm). Needs Docker — it cannot run on GitHub Pages. See `platform/README.md`. |

## Try it
Tap a sphere → watch the reasoning trace. Use the chips (⚡ inject thermal / bearing / crack / electrical) or type in the Copilot bar:
`inject thermal n-03`, `status`, `approve`, `reject`, `select n-05`.
Physical actions (isolate / shutdown) pause for a **Sign & approve** step (WebCrypto HMAC, single-use nonce).

## Publish on GitHub Pages
1. Create a new **public** repo (e.g. `corona`) — don't add a README there.
2. Upload these files to the repo root (see guide in chat), commit to `main`.
3. Repo → **Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / `(root)` → Save**.
4. Wait ~1 minute, open `https://<username>.github.io/corona/`.
