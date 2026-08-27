"""
Two-Tier validation engine for transaction ingestion.
Tier 1: Structural and syntactic validation
Tier 2: Business and financial invariants validation
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Tuple, Optional
from uuid import UUID

from src.models.transaction import (
    TransactionEventModel,
    QuarantineRecordModel,
    TransactionType,
    QuarantineErrorCode,
)


def validate_transaction_row(
    raw_row: Dict[str, Any],
    raw_line_number: int,
    raw_content: str,
    file_id: UUID
) -> Tuple[Optional[TransactionEventModel], Optional[QuarantineRecordModel]]:
    """
    Validates a raw dictionary representing a single CSV row against Tier 1 & Tier 2 DQ rules.
    Returns (TransactionEventModel, None) if valid, or (None, QuarantineRecordModel) if invalid.
    """
    # -------------------------------------------------------------------------
    # Tier 1: Structural Checks (Missing Fields & String-to-Type Casting)
    # -------------------------------------------------------------------------
    required_fields = ["transaction_date", "ticker", "type", "quantity", "unit_price", "currency"]
    for field in required_fields:
        val = raw_row.get(field)
        if val is None or str(val).strip() == "":
            return None, QuarantineRecordModel(
                file_id=file_id,
                raw_line_number=raw_line_number,
                raw_content=raw_content,
                validation_error_code=QuarantineErrorCode.ERR_MISSING_REQUIRED_FIELD,
            )

    raw_date_str = str(raw_row["transaction_date"]).strip()
    try:
        parsed_date = datetime.strptime(raw_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_STRUCTURAL_PARSING_FAILED,
        )

    try:
        parsed_quantity = Decimal(str(raw_row["quantity"]).strip())
        parsed_price = Decimal(str(raw_row["unit_price"]).strip())
        
        op_cost_val = raw_row.get("operational_cost", "0.0000")
        op_cost_str = "0.0000" if op_cost_val is None or str(op_cost_val).strip() == "" else str(op_cost_val).strip()
        parsed_op_cost = Decimal(op_cost_str)
    except (InvalidOperation, TypeError, ValueError):
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_STRUCTURAL_PARSING_FAILED,
        )

    # -------------------------------------------------------------------------
    # Tier 2: Domain Business Invariants
    # -------------------------------------------------------------------------
    raw_type_str = str(raw_row["type"]).strip().upper()
    try:
        parsed_type = TransactionType(raw_type_str)
    except ValueError:
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_INVALID_TRANSACTION_TYPE,
        )

    if parsed_quantity <= Decimal("0"):
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_NON_POSITIVE_QUANTITY,
        )

    if parsed_price <= Decimal("0"):
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_NON_POSITIVE_PRICE,
        )

    currency_code = str(raw_row["currency"]).strip().upper()
    if len(currency_code) != 3:
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_UNSUPPORTED_CURRENCY,
        )

    if parsed_date > date.today():
        return None, QuarantineRecordModel(
            file_id=file_id,
            raw_line_number=raw_line_number,
            raw_content=raw_content,
            validation_error_code=QuarantineErrorCode.ERR_FUTURE_TRANSACTION_DATE,
        )

    # All validations passed: Build domain model
    ticker_clean = str(raw_row["ticker"]).strip().upper()
    valid_event = TransactionEventModel(
        file_id=file_id,
        transaction_date=parsed_date,
        ticker=ticker_clean,
        type=parsed_type,
        quantity=parsed_quantity,
        unit_price_amount=parsed_price,
        unit_price_currency=currency_code,
        operational_cost_amount=parsed_op_cost,
        operational_cost_currency=currency_code,
    )
    return valid_event, None
