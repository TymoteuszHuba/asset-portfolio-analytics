"""
Unit tests for Tier 1 and Tier 2 Data Quality Validators.
"""

from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest

from src.models.transaction import QuarantineErrorCode, TransactionType
from src.validation.validators import validate_transaction_row


@pytest.fixture
def sample_file_id():
    return uuid.uuid4()


def test_valid_buy_transaction(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "10.5",
        "unit_price": "180.25",
        "currency": "USD",
        "operational_cost": "1.50"
    }
    raw_content = "2026-05-10,AAPL,BUY,10.5,180.25,USD,1.50"
    
    event, quarantine = validate_transaction_row(raw_row, 2, raw_content, sample_file_id)
    
    assert quarantine is None
    assert event is not None
    assert event.ticker == "AAPL"
    assert event.type == TransactionType.BUY
    assert event.quantity == Decimal("10.5")
    assert event.unit_price_amount == Decimal("180.25")
    assert event.unit_price_currency == "USD"


def test_missing_required_field(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "",  # Blank ticker
        "type": "BUY",
        "quantity": "10",
        "unit_price": "100",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 3, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_MISSING_REQUIRED_FIELD


def test_invalid_date_format(sample_file_id):
    raw_row = {
        "transaction_date": "10/05/2026",  # Invalid format (expects YYYY-MM-DD)
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "10",
        "unit_price": "100",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 4, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_STRUCTURAL_PARSING_FAILED


def test_invalid_transaction_type(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "AAPL",
        "type": "UNKNOWN_ACTION",
        "quantity": "10",
        "unit_price": "100",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 5, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_INVALID_TRANSACTION_TYPE


def test_negative_quantity(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "-5.0",
        "unit_price": "100",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 6, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_NON_POSITIVE_QUANTITY


def test_negative_unit_price(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "10",
        "unit_price": "-10.0",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 7, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_NON_POSITIVE_PRICE


def test_unsupported_currency(sample_file_id):
    raw_row = {
        "transaction_date": "2026-05-10",
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "10",
        "unit_price": "100",
        "currency": "USDOLLARS"  # Length != 3
    }
    event, quarantine = validate_transaction_row(raw_row, 8, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_UNSUPPORTED_CURRENCY


def test_future_transaction_date(sample_file_id):
    future_date_str = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
    raw_row = {
        "transaction_date": future_date_str,
        "ticker": "AAPL",
        "type": "BUY",
        "quantity": "10",
        "unit_price": "100",
        "currency": "USD"
    }
    event, quarantine = validate_transaction_row(raw_row, 9, "raw text", sample_file_id)
    
    assert event is None
    assert quarantine is not None
    assert quarantine.validation_error_code == QuarantineErrorCode.ERR_FUTURE_TRANSACTION_DATE
