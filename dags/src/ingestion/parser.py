"""
CSV Report Parser module for ingestion of broker CSV files.
"""

import csv
from typing import Dict, List, Tuple, Any
from uuid import UUID

from src.models.transaction import TransactionEventModel, QuarantineRecordModel
from src.validation.validators import validate_transaction_row


def _normalize_row(raw_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes raw broker export headers and values to standard DWH expected keys.
    """
    normalized = dict(raw_row)
    header_map = {
        "Transaction Date": "transaction_date",
        "date": "transaction_date",
        "Action": "type",
        "action": "type",
        "Ticker": "ticker",
        "symbol": "ticker",
        "No. of shares": "quantity",
        "shares": "quantity",
        "Price / share": "unit_price",
        "price": "unit_price",
        "Currency (Price / share)": "currency",
        "Charge amount": "operational_cost",
    }
    for orig, target in header_map.items():
        if orig in raw_row and (target not in normalized or not normalized[target]):
            normalized[target] = raw_row[orig]

    if "type" in normalized and normalized["type"]:
        action_str = str(normalized["type"]).strip().lower()
        if "buy" in action_str:
            normalized["type"] = "BUY"
        elif "sell" in action_str:
            normalized["type"] = "SELL"
        elif "dividend" in action_str:
            normalized["type"] = "DIVIDEND"
            if not normalized.get("quantity") or str(normalized.get("quantity")).strip() in ["", "0", "0.0", "None"]:
                normalized["quantity"] = "1"
            if not normalized.get("ticker") or str(normalized.get("ticker")).strip() in ["", "None"]:
                normalized["ticker"] = "CASH"

    if "currency" not in normalized or not str(normalized.get("currency")).strip():
        normalized["currency"] = "USD"

    return normalized


def parse_broker_csv(
    file_path: str,
    file_id: UUID
) -> Tuple[List[TransactionEventModel], List[QuarantineRecordModel]]:
    """
    Parses a raw broker CSV report file and applies Tier 1 & Tier 2 validations.
    Returns a tuple of (valid_events, quarantine_records).
    """
    valid_events: List[TransactionEventModel] = []
    quarantine_records: List[QuarantineRecordModel] = []

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        # Save raw line strings for exact quarantine logging
        lines = f.readlines()

    if not lines:
        return valid_events, quarantine_records

    # Parse header line to determine CSV field names
    reader = csv.DictReader(lines)

    for idx, row in enumerate(reader, start=2):
        # Retrieve original unparsed text line for this index
        raw_line_text = lines[idx - 1].strip() if idx - 1 < len(lines) else str(row)

        normalized_row = _normalize_row(row)

        valid_event, quarantine_record = validate_transaction_row(
            raw_row=normalized_row,
            raw_line_number=idx,
            raw_content=raw_line_text,
            file_id=file_id,
        )

        if valid_event:
            valid_events.append(valid_event)
        elif quarantine_record:
            quarantine_records.append(quarantine_record)

    return valid_events, quarantine_records
