"""
Domain models and enums for transaction ingestion and quarantine engine.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"


class QuarantineErrorCode(str, Enum):
    ERR_STRUCTURAL_PARSING_FAILED = "ERR_STRUCTURAL_PARSING_FAILED"
    ERR_MISSING_REQUIRED_FIELD = "ERR_MISSING_REQUIRED_FIELD"
    ERR_INVALID_TRANSACTION_TYPE = "ERR_INVALID_TRANSACTION_TYPE"
    ERR_NON_POSITIVE_QUANTITY = "ERR_NON_POSITIVE_QUANTITY"
    ERR_NON_POSITIVE_PRICE = "ERR_NON_POSITIVE_PRICE"
    ERR_UNSUPPORTED_CURRENCY = "ERR_UNSUPPORTED_CURRENCY"
    ERR_FUTURE_TRANSACTION_DATE = "ERR_FUTURE_TRANSACTION_DATE"


class BrokerReportStatus(str, Enum):
    PROCESSED = "PROCESSED"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    FAILED = "FAILED"


class TransactionEventModel(BaseModel):
    """
    Normalized domain transaction model corresponding to core.transaction_events.
    """
    transaction_id: Optional[UUID] = None
    file_id: Optional[UUID] = None
    transaction_date: date
    ticker: str = Field(..., min_length=1, max_length=50)
    type: TransactionType
    quantity: Decimal = Field(..., gt=0)
    unit_price_amount: Decimal = Field(..., gt=0)
    unit_price_currency: str = Field(..., min_length=3, max_length=3)
    operational_cost_amount: Decimal = Field(default=Decimal("0.0000"), ge=0)
    operational_cost_currency: str = Field(default="EUR", min_length=3, max_length=3)


class QuarantineRecordModel(BaseModel):
    """
    Quarantine record model corresponding to core.quarantine_records.
    """
    record_id: Optional[UUID] = None
    file_id: UUID
    raw_line_number: int
    raw_content: str
    validation_error_code: QuarantineErrorCode
    quarantined_at: Optional[datetime] = None
