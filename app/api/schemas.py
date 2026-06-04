# app/api/schemas.py
"""
Pydantic v2 schemas for the fraud detection API.

Design decisions:
1. extra="forbid" on all request models — reject any field not in the schema.
   This prevents prompt injection, parameter pollution, and field smuggling.
   A malicious actor cannot add unexpected fields that might confuse processing.

2. Strict field types — amount is float, not str. Pydantic v2 will not
   coerce "50000" (string) to 50000.0 (float) in strict mode.
   This catches malformed payloads before they reach Kafka.

3. TransactionType enum — only valid transaction types are accepted.
   Anything else is rejected at the API boundary with a 422 error.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionType(str, Enum):
    """
    Valid PaySim transaction types.
    Using an Enum means only these exact strings are accepted.
    Anything else — "wire_transfer", "hack", "TEST" — is rejected.
    """
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    DEBIT = "DEBIT"
    PAYMENT = "PAYMENT"
    TRANSFER = "TRANSFER"


class TransactionRequest(BaseModel):
    """
    Incoming transaction submitted for fraud screening.

    extra="forbid" is the security firewall:
    - Client sends {"amount": 1000, "evil_field": "injection"} → 422 rejected
    - Client sends {"amount": 1000} → accepted

    This is Pydantic v2 syntax for model configuration.
    In Pydantic v1 this was class Config: extra = "forbid"
    """
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Unique transaction identifier",
        examples=["TXN-2026-001"],
    )
    step: int = Field(
        ...,
        ge=1,
        description="Time step (1 unit = 1 hour)",
    )
    type: TransactionType = Field(
        ...,
        description="Transaction type",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount in local currency",
        examples=[150000.00],
    )
    name_orig: str = Field(
        ...,
        description="Originating account identifier",
        examples=["C1234567890"],
    )
    oldbalance_org: float = Field(
        ...,
        ge=0,
        description="Sender balance before transaction",
    )
    newbalance_orig: float = Field(
        ...,
        ge=0,
        description="Sender balance after transaction",
    )
    name_dest: str = Field(
        ...,
        description="Destination account identifier",
        examples=["C9876543210"],
    )
    oldbalance_dest: float = Field(
        ...,
        ge=0,
        description="Recipient balance before transaction",
    )
    newbalance_dest: float = Field(
        ...,
        ge=0,
        description="Recipient balance after transaction",
    )

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        """
        Explicit validator as documentation — even though gt=0 handles it.
        Shows clearly in API docs that negative amounts are rejected.
        """
        if v <= 0:
            raise ValueError("Transaction amount must be positive")
        return round(v, 2)


class TransactionResponse(BaseModel):
    """Response returned immediately after publishing to Kafka."""
    transaction_id: str
    status: str
    message: str
    kafka_partition: Optional[int] = None
    kafka_offset: Optional[int] = None
    submitted_at: datetime


class FraudResultResponse(BaseModel):
    """
    Complete fraud assessment result.
    Returned when the client polls for results after submission.
    """
    transaction_id: str
    fraud_probability: float
    is_fraud: bool
    risk_level: str
    is_anomalous: bool
    anomaly_severity: str
    top_reasons: list[dict]
    explanation_text: str
    scored_at: datetime
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    env: str
    fraud_model_loaded: bool
    anomaly_model_loaded: bool
    kafka_connected: bool