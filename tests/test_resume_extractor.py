"""Unit tests for the ResumeExtractor verifying section parsing, contact extraction, and dates."""

import pytest
from app.pipeline.extractors.resume_extractor import ResumeExtractor


def test_section_detection() -> None:
    """Tests section headers detection, casing mappings, and fallbacks."""
    extractor = ResumeExtractor()

    # 1. EXPERIENCE header detection
    text_exp = "John Doe\nEXPERIENCE\nWorked at Google"
    sections = extractor._detect_sections(text_exp)
    assert "EXPERIENCE" in sections
    assert sections["EXPERIENCE"] == "Worked at Google"

    # 2. No headers fallback -> FULL_DOCUMENT
    text_no_hdr = "John Doe\nSimple text without any headers."
    sections_no = extractor._detect_sections(text_no_hdr)
    assert "FULL_DOCUMENT" in sections_no
    assert extractor.no_sections_detected is True

    # 3. Mixed case matching check
    text_mixed = "John Doe\nSkills:\nPython, JavaScript"
    sections_mixed = extractor._detect_sections(text_mixed)
    # "Skills:" matches keyword "skills" (case-insensitive) and should map to canonical "SKILLS"
    assert "SKILLS" in sections_mixed
    assert sections_mixed["SKILLS"] == "Python, JavaScript"


def test_contact_block_extraction() -> None:
    """Tests email, phone, and profile URL regex extraction in contact blocks."""
    extractor = ResumeExtractor()

    contact_text = """
    Vidhi Bhutia
    Email: vidhibhutia2407@gmail.com
    Phone: +919685856291
    LinkedIn: linkedin.com/in/vidhi-bhutia
    """

    claims = extractor._extract_contact(contact_text, "resume.pdf")

    # 1. Email check
    email_claim = next((c for c in claims if c.field == "email"), None)
    assert email_claim is not None
    assert email_claim.raw_value == "vidhibhutia2407@gmail.com"

    # 2. Phone check
    phone_claim = next((c for c in claims if c.field == "phone"), None)
    assert phone_claim is not None
    assert phone_claim.raw_value == "+919685856291"

    # 3. LinkedIn link check
    linkedin_claim = next((c for c in claims if c.field == "linkedin_url"), None)
    assert linkedin_claim is not None
    assert linkedin_claim.raw_value == "linkedin.com/in/vidhi-bhutia"


def test_date_range_parsing() -> None:
    """Tests the custom date parser on various formats inside experience blocks."""
    extractor = ResumeExtractor()

    # 1. "May 2025 - July 2025" -> start: "2025-05", end: "2025-07"
    exp_text_1 = "Developer\nGoogle\nMay 2025 - July 2025"
    entries_1 = extractor._extract_experience(exp_text_1, "resume.pdf")
    assert len(entries_1) == 1
    assert entries_1[0].start == "2025-05"
    assert entries_1[0].end == "2025-07"

    # 2. "Feb 2026 - Present" -> start: "2026-02", end: None
    exp_text_2 = "Lead\nAmazon\nFeb 2026 - Present"
    entries_2 = extractor._extract_experience(exp_text_2, "resume.pdf")
    assert len(entries_2) == 1
    assert entries_2[0].start == "2026-02"
    assert entries_2[0].end is None

    # 3. "2022 - 2026" -> start: "2022", end: "2026"
    exp_text_3 = "Architect\nNetflix\n2022 - 2026"
    entries_3 = extractor._extract_experience(exp_text_3, "resume.pdf")
    assert len(entries_3) == 1
    assert entries_3[0].start == "2022"
    assert entries_3[0].end == "2026"
