# Wallet Service (Closed-Loop Credits)

A production-style wallet service for virtual in-app credits (gaming/loyalty use cases), with:
- ACID transactional transfers
- Double-entry ledger for auditability
- Idempotent write endpoints
- Concurrency-safe balance updates
- Dockerized Postgres + API bootstrapping

## Tech Choice
- API: FastAPI (Python)
- DB: PostgreSQL
- Data layer: SQLAlchemy + SQL

Why this stack:
- PostgreSQL provides robust transactional guarantees and row-level locking.
- FastAPI is lightweight and fast for high-throughput internal APIs.
- SQL-centric transfer logic keeps critical consistency rules explicit and auditable.

## Data Model Highlights
- `wallet_balances` stores current snapshot balance per `(wallet_id, asset_id)`.
- `transactions` stores each transfer business event.
- `ledger_entries` stores a debit + credit pair for every transaction (double entry).
- `idempotency_records` guarantees safe retry semantics.

## Concurrency Strategy
- Every transfer runs in a single DB transaction using `SERIALIZABLE` isolation.
- Source and destination balance rows are locked with `FOR UPDATE`.
- Rows are always locked in deterministic wallet-id order to reduce deadlock risk.
- Non-negative balance invariant enforced by:
  1. Explicit funds check under row lock.
  2. DB-level `CHECK (balance >= 0)` constraint.

## Idempotency Strategy
Client sends `idempotency_key` in request body.
- First request stores `idempotency_key + request_fingerprint`.
- Retries with same key + same payload return stored response (`replayed=true`).
- Same key + different payload returns `409` conflict.

## Seeded Data
`sql/seed.sql` seeds:
1. Asset types: `GOLD`, `DIAMOND`, `LOYALTY`
2. System wallets: `Treasury`, `Revenue`
3. Users: `alice`, `bob` with initial balances

## Run With Docker (Recommended)
```bash
docker compose up --build
```

API will be available at `http://localhost:8000`.

## Local Run (Without Docker)
1. Start PostgreSQL and create DB `wallet` with user/password `wallet` (or set your own env values).
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Apply schema + seed:
```bash
bash setup.sh
```

On Windows PowerShell:
```powershell
.\setup.ps1
```
4. Start API:
```bash
uvicorn app.main:app --reload
```

If needed, override DB URL:
```bash
export DATABASE_URL=postgresql+psycopg://wallet:wallet@localhost:5432/wallet
```

## API Endpoints
- `GET /health`
- `GET /v1/wallets/{user_id}/balances`
- `POST /v1/wallets/topups`
- `POST /v1/wallets/bonuses`
- `POST /v1/wallets/spends`
- `GET /v1/transactions/{transaction_id}`

### Example: Top-up
```bash
curl -X POST http://localhost:8000/v1/wallets/topups \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "asset_code": "GOLD",
    "amount": 100,
    "idempotency_key": "topup-1-001",
    "reference": "payment_abc123",
    "metadata": {"channel": "card"}
  }'
```

### Example: Spend
```bash
curl -X POST http://localhost:8000/v1/wallets/spends \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "asset_code": "GOLD",
    "amount": 30,
    "idempotency_key": "spend-1-001",
    "reference": "item_sword",
    "metadata": {"item_id": "sword_01"}
  }'
```

## Notes
- Amounts are integer minor units; no floating-point arithmetic is used.
- This implementation is transfer-based (closed-loop), no user-to-user transfer endpoint is exposed.
- For internet-facing production, add authn/authz, rate limiting, structured logging, and observability.

# Render Deployment

This repo includes `render.yaml` for one-click Render Blueprint deploy.

1. Push latest code to GitHub.
2. In Render: New + -> Blueprint -> select this repo.
3. Render provisions:
   - `dino-wallet-db` (PostgreSQL)
   - `dino-wallet-api` (Docker web service)
4. `DATABASE_URL` is wired automatically from the DB.
5. `AUTO_SEED=true` runs schema + seed on API startup (idempotent).

After deploy, open:
- `/health`
- `/docs`

Note: free instances may sleep when idle.
