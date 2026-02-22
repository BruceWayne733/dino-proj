import hashlib
import json
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@dataclass
class WalletContext:
    user_wallet_id: int
    source_wallet_id: int
    asset_id: int
    asset_code: str


def _fingerprint(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _get_wallet_context(db: Session, user_id: int, asset_code: str, source_owner_ref: str) -> WalletContext:
    row = db.execute(
        text(
            """
            SELECT uw.id AS user_wallet_id, sw.id AS source_wallet_id, a.id AS asset_id, a.code AS asset_code
            FROM wallets uw
            JOIN wallets sw ON sw.owner_type = 'SYSTEM' AND sw.owner_ref = :source_owner_ref
            JOIN assets a ON a.code = :asset_code
            WHERE uw.owner_type = 'USER' AND uw.owner_ref = :user_ref
            """
        ),
        {"source_owner_ref": source_owner_ref, "asset_code": asset_code, "user_ref": f"user:{user_id}"},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="User wallet, asset, or source wallet not found")

    return WalletContext(
        user_wallet_id=row["user_wallet_id"],
        source_wallet_id=row["source_wallet_id"],
        asset_id=row["asset_id"],
        asset_code=row["asset_code"],
    )


def _ensure_balance_rows(db: Session, wallet_ids: list[int], asset_id: int) -> None:
    for wallet_id in wallet_ids:
        db.execute(
            text(
                """
                INSERT INTO wallet_balances (wallet_id, asset_id, balance)
                VALUES (:wallet_id, :asset_id, 0)
                ON CONFLICT (wallet_id, asset_id) DO NOTHING
                """
            ),
            {"wallet_id": wallet_id, "asset_id": asset_id},
        )


def _lock_balances_in_order(db: Session, wallet_a: int, wallet_b: int, asset_id: int) -> None:
    first, second = sorted([wallet_a, wallet_b])
    db.execute(
        text(
            """
            SELECT wallet_id
            FROM wallet_balances
            WHERE asset_id = :asset_id AND wallet_id IN (:first, :second)
            ORDER BY wallet_id
            FOR UPDATE
            """
        ),
        {"asset_id": asset_id, "first": first, "second": second},
    ).all()


def _read_balance(db: Session, wallet_id: int, asset_id: int) -> int:
    row = db.execute(
        text(
            """
            SELECT balance
            FROM wallet_balances
            WHERE wallet_id = :wallet_id AND asset_id = :asset_id
            """
        ),
        {"wallet_id": wallet_id, "asset_id": asset_id},
    ).first()
    if row is None:
        return 0
    return int(row[0])


def _apply_transfer(
    db: Session,
    tx_type: str,
    asset_id: int,
    amount: int,
    from_wallet_id: int,
    to_wallet_id: int,
    reference: str | None,
    metadata: dict,
) -> tuple[str, str]:
    current_from = _read_balance(db, from_wallet_id, asset_id)
    if current_from < amount:
        raise HTTPException(status_code=409, detail="Insufficient balance")

    db.execute(
        text(
            """
            UPDATE wallet_balances
            SET balance = balance - :amount, updated_at = now()
            WHERE wallet_id = :wallet_id AND asset_id = :asset_id
            """
        ),
        {"amount": amount, "wallet_id": from_wallet_id, "asset_id": asset_id},
    )
    db.execute(
        text(
            """
            UPDATE wallet_balances
            SET balance = balance + :amount, updated_at = now()
            WHERE wallet_id = :wallet_id AND asset_id = :asset_id
            """
        ),
        {"amount": amount, "wallet_id": to_wallet_id, "asset_id": asset_id},
    )

    tx_id = str(uuid.uuid4())
    created_at = db.execute(
        text(
            """
            INSERT INTO transactions (id, tx_type, asset_id, amount, from_wallet_id, to_wallet_id, reference, metadata)
            VALUES (:id, :tx_type, :asset_id, :amount, :from_wallet_id, :to_wallet_id, :reference, CAST(:metadata AS jsonb))
            RETURNING created_at
            """
        ),
        {
            "id": tx_id,
            "tx_type": tx_type,
            "asset_id": asset_id,
            "amount": amount,
            "from_wallet_id": from_wallet_id,
            "to_wallet_id": to_wallet_id,
            "reference": reference,
            "metadata": json.dumps(metadata),
        },
    ).scalar_one()

    db.execute(
        text(
            """
            INSERT INTO ledger_entries (transaction_id, wallet_id, asset_id, entry_type, amount)
            VALUES
                (:tx_id, :from_wallet_id, :asset_id, 'DEBIT', :amount),
                (:tx_id, :to_wallet_id, :asset_id, 'CREDIT', :amount)
            """
        ),
        {
            "tx_id": tx_id,
            "from_wallet_id": from_wallet_id,
            "to_wallet_id": to_wallet_id,
            "asset_id": asset_id,
            "amount": amount,
        },
    )
    return tx_id, created_at.isoformat()


def execute_transfer(
    db: Session,
    tx_type: str,
    user_id: int,
    asset_code: str,
    amount: int,
    idempotency_key: str,
    reference: str | None,
    metadata: dict,
    source_owner_ref: str,
    source_to_user: bool,
) -> dict:
    payload = {
        "tx_type": tx_type,
        "user_id": user_id,
        "asset_code": asset_code,
        "amount": amount,
        "reference": reference,
        "metadata": metadata,
        "source_owner_ref": source_owner_ref,
        "source_to_user": source_to_user,
    }
    request_fp = _fingerprint(payload)

    try:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        db.execute(
            text(
                """
                INSERT INTO idempotency_records (idempotency_key, request_fingerprint)
                VALUES (:key, :fp)
                ON CONFLICT DO NOTHING
                """
            ),
            {"key": idempotency_key, "fp": request_fp},
        )

        idempotency = db.execute(
            text(
                """
                SELECT idempotency_key, request_fingerprint, response
                FROM idempotency_records
                WHERE idempotency_key = :key
                FOR UPDATE
                """
            ),
            {"key": idempotency_key},
        ).mappings().first()

        if idempotency is None:
            raise HTTPException(status_code=500, detail="Failed to acquire idempotency record")

        if idempotency["request_fingerprint"] != request_fp:
            raise HTTPException(status_code=409, detail="Idempotency key re-used with different payload")

        if idempotency["response"] is not None:
            response = dict(idempotency["response"])
            response["replayed"] = True
            db.commit()
            return response

        ctx = _get_wallet_context(db, user_id, asset_code, source_owner_ref)

        if source_to_user:
            from_wallet_id = ctx.source_wallet_id
            to_wallet_id = ctx.user_wallet_id
        else:
            from_wallet_id = ctx.user_wallet_id
            to_wallet_id = ctx.source_wallet_id

        _ensure_balance_rows(db, [from_wallet_id, to_wallet_id], ctx.asset_id)
        _lock_balances_in_order(db, from_wallet_id, to_wallet_id, ctx.asset_id)

        tx_id, created_at = _apply_transfer(
            db=db,
            tx_type=tx_type,
            asset_id=ctx.asset_id,
            amount=amount,
            from_wallet_id=from_wallet_id,
            to_wallet_id=to_wallet_id,
            reference=reference,
            metadata=metadata,
        )

        user_balance_after = _read_balance(db, ctx.user_wallet_id, ctx.asset_id)
        response = {
            "transaction_id": tx_id,
            "tx_type": tx_type,
            "user_id": user_id,
            "asset_code": ctx.asset_code,
            "amount": amount,
            "from_wallet_id": from_wallet_id,
            "to_wallet_id": to_wallet_id,
            "user_balance_after": user_balance_after,
            "created_at": created_at,
            "replayed": False,
        }

        db.execute(
            text(
                """
                UPDATE idempotency_records
                SET transaction_id = :tx_id,
                    response = CAST(:response AS jsonb),
                    updated_at = now()
                WHERE idempotency_key = :key
                """
            ),
            {"tx_id": tx_id, "response": json.dumps(response), "key": idempotency_key},
        )

        db.commit()
        return response
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violation while processing transaction")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal error while processing transaction")


def get_user_balances(db: Session, user_id: int) -> dict:
    rows = db.execute(
        text(
            """
            SELECT a.code, wb.balance
            FROM wallets w
            JOIN wallet_balances wb ON wb.wallet_id = w.id
            JOIN assets a ON a.id = wb.asset_id
            WHERE w.owner_type = 'USER' AND w.owner_ref = :owner_ref
            ORDER BY a.code
            """
        ),
        {"owner_ref": f"user:{user_id}"},
    ).all()

    if not rows:
        exists = db.execute(
            text("SELECT 1 FROM wallets WHERE owner_type = 'USER' AND owner_ref = :owner_ref"),
            {"owner_ref": f"user:{user_id}"},
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="User wallet not found")

    return {
        "user_id": user_id,
        "balances": [{"asset_code": r[0], "balance": int(r[1])} for r in rows],
    }


def get_transaction(db: Session, transaction_id: str) -> dict:
    row = db.execute(
        text(
            """
            SELECT t.id, t.tx_type, a.code, t.amount, t.from_wallet_id, t.to_wallet_id, t.reference, t.metadata, t.created_at
            FROM transactions t
            JOIN assets a ON a.id = t.asset_id
            WHERE t.id = CAST(:tx_id AS uuid)
            """
        ),
        {"tx_id": transaction_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "transaction_id": str(row["id"]),
        "tx_type": row["tx_type"],
        "asset_code": row["code"],
        "amount": int(row["amount"]),
        "from_wallet_id": int(row["from_wallet_id"]),
        "to_wallet_id": int(row["to_wallet_id"]),
        "reference": row["reference"],
        "metadata": row["metadata"],
        "created_at": row["created_at"].isoformat(),
    }

