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


def test_inline_company_date_range_parsing() -> None:
    """Tests that company name inline with date range on the same line is correctly parsed."""
    extractor = ResumeExtractor()

    # 1. "People Prudent Feb 2026 - Present" -> company: "People Prudent"
    exp_text = "People Prudent Feb 2026 - Present\nIT & Software Intern Pune, India\nBullet point 1\nBullet point 2"
    entries = extractor._extract_experience(exp_text, "resume.pdf")
    assert len(entries) == 1
    assert entries[0].company == "People Prudent"
    assert entries[0].title == "IT & Software Intern Pune, India"
    assert entries[0].start == "2026-02"
    assert entries[0].end is None

    # 2. "Morgan Stanley May 2025 - July 2025" -> company: "Morgan Stanley"
    exp_text_2 = "Morgan Stanley May 2025 - July 2025\nTechnology Analyst Intern Bengaluru, India\nSome summary text"
    entries_2 = extractor._extract_experience(exp_text_2, "resume.pdf")
    assert len(entries_2) == 1
    assert entries_2[0].company == "Morgan Stanley"
    assert entries_2[0].title == "Technology Analyst Intern Bengaluru, India"
    assert entries_2[0].start == "2025-05"
    assert entries_2[0].end == "2025-07"


def test_single_newline_separated_experience_and_education_blocks() -> None:
    """Tests parsing experience and education when entries are separated by single newlines only."""
    extractor = ResumeExtractor()

    # 1. Experience
    exp_text = (
        "People Prudent Feb 2026 - Present\n"
        "IT & Software Intern Pune, India\n"
        "• Bullet point 1\n"
        "Morgan Stanley May 2025 - July 2025\n"
        "Technology Analyst Intern Bengaluru, India\n"
        "• Bullet point 2\n"
    )
    entries = extractor._extract_experience(exp_text, "resume.pdf")
    assert len(entries) == 2
    assert entries[0].company == "People Prudent"
    assert entries[0].start == "2026-02"
    assert entries[1].company == "Morgan Stanley"
    assert entries[1].start == "2025-05"

    # 2. Education
    edu_text = (
        "Year Degree/Certificate Institute CGPA/%\n"
        "2022 - 2026 B.Tech in CSE & Business Systems Vellore Institute of Technology, Vellore 9.11/10\n"
        "2021 Class XII (CBSE) Scindia Kanya Vidyalaya, Gwalior 95.8%\n"
    )
    entries_edu = extractor._extract_education(edu_text)
    assert len(entries_edu) == 2
    assert entries_edu[0].institution == "Vellore Institute of Technology"
    assert entries_edu[0].degree == "B.Tech in CSE & Business Systems"
    assert entries_edu[0].end_year == 2026
    assert entries_edu[1].institution == "Scindia Kanya Vidyalaya"
    assert entries_edu[1].degree == "Class XII (CBSE)"
    assert entries_edu[1].end_year == 2021


