"""
CSV Report Parser module for ingestion of broker CSV files.
"""

import csv
from typing import Dict, List, Tuple, Any
from uuid import UUID

from src.models.transaction import TransactionEventModel, QuarantineRecordModel
from src.validation.validators import validate_transaction_row


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
    header_line = lines[0]
    reader = csv.DictReader(lines)

    for idx, row in enumerate(reader, start=2):
        # Retrieve original unparsed text line for this index
        raw_line_text = lines[idx - 1].strip() if idx - 1 < len(lines) else str(row)

        valid_event, quarantine_record = validate_transaction_row(
            raw_row=row,
            raw_line_number=idx,
            raw_content=raw_line_text,
            file_id=file_id,
        )

        if valid_event:
            valid_events.append(valid_event)
        elif quarantine_record:
            quarantine_records.append(quarantine_record)

    return valid_events, quarantine_records
