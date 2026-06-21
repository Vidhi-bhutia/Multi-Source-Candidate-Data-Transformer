"""Unit tests verifying the candidate transformer normalizer routines."""

import pytest
from app.pipeline.normalizer import Normalizer
from app.pipeline.models import NormalizationStatus


def test_normalize_phone() -> None:
    """Tests _normalize_phone E.164 standardization and invalid formats."""
    normalizer = Normalizer()

    # 1. "+919685856291" -> "+919685856291"
    val, status, _, _ = normalizer._normalize_phone("+919685856291")
    assert val == "+919685856291"
    assert status == NormalizationStatus.SUCCESS

    # 2. "9685856291" -> "+919685856291"
    val, status, _, _ = normalizer._normalize_phone("9685856291")
    assert val == "+919685856291"
    assert status == NormalizationStatus.SUCCESS

    # 3. "(415) 555-0100" -> "+14155550100"
    val, status, _, _ = normalizer._normalize_phone("(415) 555-0100")
    assert val == "+14155550100"
    assert status == NormalizationStatus.SUCCESS

    # 4. "N/A" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_phone("N/A")
    assert val is None
    assert status == NormalizationStatus.FAILED

    # 5. "call me" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_phone("call me")
    assert val is None
    assert status == NormalizationStatus.FAILED

    # 6. "555-HIRE" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_phone("555-HIRE")
    assert val is None
    assert status == NormalizationStatus.FAILED


def test_normalize_email() -> None:
    """Tests _normalize_email cleaning, validation, and multi-email selection."""
    normalizer = Normalizer()

    # 1. "VIDHI@GMAIL.COM" -> "vidhi@gmail.com"
    val, status, _, _ = normalizer._normalize_email("VIDHI@GMAIL.COM")
    assert val == "vidhi@gmail.com"
    assert status == NormalizationStatus.SUCCESS

    # 2. "  vidhi@gmail.com  " -> "vidhi@gmail.com"
    val, status, _, _ = normalizer._normalize_email("  vidhi@gmail.com  ")
    assert val == "vidhi@gmail.com"
    assert status == NormalizationStatus.SUCCESS

    # 3. "not-an-email" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_email("not-an-email")
    assert val is None
    assert status == NormalizationStatus.FAILED

    # 4. "vidhi@gmail.com; other@gmail.com" -> "vidhi@gmail.com"
    val, status, _, _ = normalizer._normalize_email("vidhi@gmail.com; other@gmail.com")
    assert val == "vidhi@gmail.com"
    assert status == NormalizationStatus.SUCCESS


def test_normalize_date() -> None:
    """Tests _normalize_date conversion patterns, partial fits, and present markers."""
    normalizer = Normalizer()

    # 1. "Jan 2023" -> "2023-01"
    val, status, _, _ = normalizer._normalize_date("Jan 2023")
    assert val == "2023-01"
    assert status == NormalizationStatus.SUCCESS

    # 2. "February 2022" -> "2022-02"
    val, status, _, _ = normalizer._normalize_date("February 2022")
    assert val == "2022-02"
    assert status == NormalizationStatus.SUCCESS

    # 3. "2023" -> "2023-01", status PARTIAL
    val, status, _, _ = normalizer._normalize_date("2023")
    assert val == "2023-01"
    assert status == NormalizationStatus.PARTIAL

    # 4. "Present" -> None, status NOT_APPLICABLE
    val, status, _, _ = normalizer._normalize_date("Present")
    assert val is None
    assert status == NormalizationStatus.NOT_APPLICABLE

    # 5. "present" -> None (case-insensitive)
    val, status, _, _ = normalizer._normalize_date("present")
    assert val is None
    assert status == NormalizationStatus.NOT_APPLICABLE

    # 6. "Current" -> None
    val, status, _, _ = normalizer._normalize_date("Current")
    assert val is None
    assert status == NormalizationStatus.NOT_APPLICABLE

    # 7. "garbage" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_date("garbage")
    assert val is None
    assert status == NormalizationStatus.FAILED


def test_normalize_name() -> None:
    """Tests _normalize_name parsing, inversions, and spacing cleanup."""
    normalizer = Normalizer()

    # 1. "Bhutia, Vidhi" -> "Vidhi Bhutia"
    val, status, _, _ = normalizer._normalize_name("Bhutia, Vidhi")
    assert val == "Vidhi Bhutia"
    assert status == NormalizationStatus.SUCCESS

    # 2. "VIDHI BHUTIA" -> "Vidhi Bhutia"
    val, status, _, _ = normalizer._normalize_name("VIDHI BHUTIA")
    assert val == "Vidhi Bhutia"
    assert status == NormalizationStatus.SUCCESS

    # 3. "  vidhi  bhutia  " -> "Vidhi Bhutia"
    val, status, _, _ = normalizer._normalize_name("  vidhi  bhutia  ")
    assert val == "Vidhi Bhutia"
    assert status == NormalizationStatus.SUCCESS

    # 4. "" -> None, status FAILED
    val, status, _, _ = normalizer._normalize_name("")
    assert val is None
    assert status == NormalizationStatus.FAILED
