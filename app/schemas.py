from typing import Any
from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    user_id: int = Field(gt=0)
    asset_code: str = Field(min_length=2, max_length=50)
    amount: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=200)
    reference: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TransactionResponse(BaseModel):
    transaction_id: str
    tx_type: str
    user_id: int
    asset_code: str
    amount: int
    from_wallet_id: int
    to_wallet_id: int
    user_balance_after: int
    created_at: str
    replayed: bool = False


class BalanceItem(BaseModel):
    asset_code: str
    balance: int


class WalletBalanceResponse(BaseModel):
    user_id: int
    balances: list[BalanceItem]

