# Corona — Self-Healing Spatial Digital Twin

![License](https://img.shields.io/badge/license-MIT-38e8ff) ![Stack](https://img.shields.io/badge/stack-Next.js%20·%20FastAPI%20·%20LangGraph%20·%20Neo4j%20·%20Kafka-0a1530) ![Security](https://img.shields.io/badge/crypto-X25519%20%2B%20ML--KEM--768-3dffa8)

**Built by [Nikhil Chary Sriramoju](https://github.com/Nikhil-creat)** · B.Tech CSE, Vaagdevi College of Engineering (2023–2027) · ML Engineer Intern @ Yuva Intern (NSDC) · Data Analytics Intern @ Thiranex
· NASSCOM/Skill India Digital Hub (AI-Data Engineering & Cloud Infrastructure Analyst) · IBM SkillsBuild (AI Fundamentals) · Reliance Foundation (AI/ML Engineer Foundation)
· [LinkedIn](https://in.linkedin.com/in/nikhil-chary-sriramoju-95041b38a)

### Highlights
- Human-approved **agentic AI swarm** (Validator → Compliance-RAG → Risk → Planner ⇄ Verifier → signed approval → Executor)
- **Zero-hallucination contract:** no evidence → the swarm abstains; actions only from an allow-list with hard bounds
- **Tamper-evident audit ledger** (SHA-256 hash chain, verify / tamper-test / export JSON)
- **Autopilot toggle** for non-physical fixes; physical actions always need a signed human decision
- Predictive failure forecast, federated-learning counter, copilot command bar
- Production stack: ViT + EfficientNet-V2 vision, temporal Graph-RAG, Redpanda, post-quantum envelopes, OpenTelemetry/Prometheus/Grafana, Docker + Helm

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
