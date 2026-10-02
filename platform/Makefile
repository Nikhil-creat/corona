.PHONY: up up-gpu down logs test lite e2e keys fmt
up:        ## full stack (CPU, simulated vision)
	docker compose up -d --build
up-gpu:    ## GPU edge inference (needs NVIDIA Container Toolkit + ./models)
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
down:
	docker compose down
logs:
	docker compose logs -f api worker vision-edge
test:      ## unit + API tests (in-memory mode, no infra needed)
	pip install -r backend/requirements.txt && pytest -q
lite:      ## single-process demo: no Kafka/Redis/Postgres/Neo4j
	USE_IN_MEMORY=true EMBEDDED_WORKER=true ENV=dev PYTHONPATH=.:backend uvicorn app.main:app --port 8000
e2e:       ## end-to-end check against a running stack
	python scripts/e2e_test.py
keys:      ## generate an ed25519 approver keypair
	PYTHONPATH=. python scripts/sign_approval.py keygen
