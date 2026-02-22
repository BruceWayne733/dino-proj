from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.bootstrap import maybe_seed_database
from app.db import get_db
from app.schemas import TransactionResponse, TransferRequest, WalletBalanceResponse
from app.service import execute_transfer, get_transaction, get_user_balances

app = FastAPI(title="Closed-Loop Wallet Service", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    maybe_seed_database()


@app.get("/")
def root() -> dict:
    return {"service": "wallet", "status": "ok", "docs": "/docs"}


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/v1/wallets/{user_id}/balances", response_model=WalletBalanceResponse)
def balances(user_id: int, db: Session = Depends(get_db)) -> dict:
    return get_user_balances(db, user_id)


@app.post("/v1/wallets/topups", response_model=TransactionResponse)
def topup(payload: TransferRequest, db: Session = Depends(get_db)) -> dict:
    return execute_transfer(
        db=db,
        tx_type="TOPUP",
        user_id=payload.user_id,
        asset_code=payload.asset_code,
        amount=payload.amount,
        idempotency_key=payload.idempotency_key,
        reference=payload.reference,
        metadata=payload.metadata,
        source_owner_ref="system:treasury",
        source_to_user=True,
    )


@app.post("/v1/wallets/bonuses", response_model=TransactionResponse)
def bonus(payload: TransferRequest, db: Session = Depends(get_db)) -> dict:
    return execute_transfer(
        db=db,
        tx_type="BONUS",
        user_id=payload.user_id,
        asset_code=payload.asset_code,
        amount=payload.amount,
        idempotency_key=payload.idempotency_key,
        reference=payload.reference,
        metadata=payload.metadata,
        source_owner_ref="system:treasury",
        source_to_user=True,
    )


@app.post("/v1/wallets/spends", response_model=TransactionResponse)
def spend(payload: TransferRequest, db: Session = Depends(get_db)) -> dict:
    return execute_transfer(
        db=db,
        tx_type="SPEND",
        user_id=payload.user_id,
        asset_code=payload.asset_code,
        amount=payload.amount,
        idempotency_key=payload.idempotency_key,
        reference=payload.reference,
        metadata=payload.metadata,
        source_owner_ref="system:revenue",
        source_to_user=False,
    )


@app.get("/v1/transactions/{transaction_id}")
def transaction(transaction_id: str, db: Session = Depends(get_db)) -> dict:
    return get_transaction(db, transaction_id)
