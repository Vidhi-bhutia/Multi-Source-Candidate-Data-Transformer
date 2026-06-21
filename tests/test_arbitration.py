"""Unit tests for the EvidenceArbitrationEngine verifying conflict resolutions and calculations."""

import pytest
from app.pipeline.arbitration import EvidenceArbitrationEngine
from app.pipeline.models import (
    Claim,
    SkillClaim,
    ExperienceEntry,
    SourceType,
    ExtractionMethod,
    ExtractionPosition,
    NormalizationStatus
)


def test_union_strategy() -> None:
    """Verifies union strategy for list fields, corroboration checks, and None value exclusion."""
    engine = EvidenceArbitrationEngine()

    # 1. Two email claims with same value -> corroboration detected, confidence boosted
    c1 = Claim(
        field="email",
        raw_value="test@example.com",
        normalized_value="test@example.com",
        source="csv",
        source_type=SourceType.STRUCTURED,
        extraction_method=ExtractionMethod.COLUMN_MAP,
        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
        confidence=0.80,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    c2 = Claim(
        field="email",
        raw_value="test@example.com",
        normalized_value="test@example.com",
        source="resume.pdf",
        source_type=SourceType.UNSTRUCTURED,
        extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
        extraction_position=ExtractionPosition.CONTACT_BLOCK,
        confidence=0.70,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    
    vals, provs = engine.arbitrate([c1, c2])
    assert vals["emails"] == ["test@example.com"]
    email_prov = next(p for p in provs if p.field == "email")
    # Base 0.80 + 0.15 corroboration bonus = 0.95
    assert abs(email_prov.winning_confidence - 0.95) < 0.001

    # 2. Two email claims with different values -> both in output list, no corroboration
    c3 = Claim(
        field="email",
        raw_value="other@example.com",
        normalized_value="other@example.com",
        source="resume.pdf",
        source_type=SourceType.UNSTRUCTURED,
        extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
        extraction_position=ExtractionPosition.CONTACT_BLOCK,
        confidence=0.60,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    # Using clean slate
    vals, provs = engine.arbitrate([c1, c3])
    # Both in union
    assert "test@example.com" in vals["emails"]
    assert "other@example.com" in vals["emails"]
    assert len(vals["emails"]) == 2

    # 3. One claim with None normalized_value -> excluded from union
    c_none = Claim(
        field="email",
        raw_value="none",
        normalized_value=None,
        source="csv",
        source_type=SourceType.STRUCTURED,
        extraction_method=ExtractionMethod.COLUMN_MAP,
        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
        confidence=0.50,
        normalization_status=NormalizationStatus.FAILED,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    vals, provs = engine.arbitrate([c1, c_none])
    assert vals["emails"] == ["test@example.com"]  # None excluded


def test_highest_confidence_strategy() -> None:
    """Verifies highest confidence winner selection, tiebreaks, and null cases."""
    engine = EvidenceArbitrationEngine()

    # 1. CSV claim 0.85 vs Resume claim 0.71 -> CSV wins
    c1 = Claim(
        field="full_name",
        raw_value="John Doe",
        normalized_value="John Doe",
        source="csv",
        source_type=SourceType.STRUCTURED,
        extraction_method=ExtractionMethod.COLUMN_MAP,
        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
        confidence=0.85,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    c2 = Claim(
        field="full_name",
        raw_value="Johnathan Doe",
        normalized_value="Johnathan Doe",
        source="resume.pdf",
        source_type=SourceType.UNSTRUCTURED,
        extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
        extraction_position=ExtractionPosition.CONTACT_BLOCK,
        confidence=0.71,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    
    vals, provs = engine.arbitrate([c1, c2])
    assert vals["full_name"] == "John Doe"
    name_prov = next(p for p in provs if p.field == "full_name")
    assert name_prov.conflict_detected is False  # diff > 0.05 (0.85 - 0.71 = 0.14)

    # 2. Both claims same value -> corroboration, confidence boost
    c2_same = Claim(
        field="full_name",
        raw_value="John Doe",
        normalized_value="John Doe",
        source="resume.pdf",
        source_type=SourceType.UNSTRUCTURED,
        extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
        extraction_position=ExtractionPosition.CONTACT_BLOCK,
        confidence=0.70,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    vals, provs = engine.arbitrate([c1, c2_same])
    assert vals["full_name"] == "John Doe"
    name_prov = next(p for p in provs if p.field == "full_name")
    # Base 0.85 + 0.15 bonus = 1.0 (capped)
    assert name_prov.winning_confidence == 1.0

    # 3. All claims have None -> output is None
    c_none = Claim(
        field="full_name",
        raw_value="none",
        normalized_value=None,
        source="csv",
        source_type=SourceType.STRUCTURED,
        extraction_method=ExtractionMethod.COLUMN_MAP,
        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
        confidence=0.85,
        normalization_status=NormalizationStatus.FAILED,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes=""
    )
    vals, provs = engine.arbitrate([c_none])
    assert vals["full_name"] is None


def test_computed_years_experience() -> None:
    """Verifies years of experience calculation, overlap merging, and Present date parsing."""
    # Set standard timeline
    engine = EvidenceArbitrationEngine(run_timestamp="2023-06-20T00:00:00Z")

    # 1. Single role Jan 2020 - Jan 2023 -> 3.0 years (37 months inclusive: 2020-01 to 2023-01 is 37 months -> 37/12 = 3.1)
    # Wait, end date is Jan 2023. Let's see: 36 months = 3.0 years
    # If Jan 2020 to Dec 2022 is 36 months. Let's use Jan 2020 - Dec 2022 to get exactly 3.0 years
    e1 = ExperienceEntry(
        company="A", title="Role A", start="2020-01", end="2022-12",
        sources=["resume"], confidence=0.80
    )
    years, prov = engine._strategy_computed_years_experience([e1], [])
    assert years == 3.0

    # 2. Two non-overlapping roles (Jan 2019 - Dec 2020, Jan 2022 - Dec 2022) -> 3.0 years
    # Jan 2019 to Dec 2020 is 24 months, Jan 2022 to Dec 2022 is 12 months. Total 36 months = 3.0 years
    e2 = ExperienceEntry(
        company="A", title="Role A", start="2019-01", end="2020-12",
        sources=["resume"], confidence=0.80
    )
    e3 = ExperienceEntry(
        company="B", title="Role B", start="2022-01", end="2022-12",
        sources=["resume"], confidence=0.80
    )
    years, prov = engine._strategy_computed_years_experience([e2, e3], [])
    assert years == 3.0

    # 3. Two overlapping roles (Jan 2019 - Jun 2022, Mar 2021 - Jun 2023)
    # Merges to Jan 2019 to Jun 2023.
    # Total months: Jan 2019 to Jun 2023 = 54 months. 54 / 12 = 4.5 years.
    # Without merging: Jan 2019 - Jun 2022 (42 months) + Mar 2021 - Jun 2023 (28 months) = 70 months (5.8 years)
    e4 = ExperienceEntry(
        company="A", title="Role A", start="2019-01", end="2022-06",
        sources=["resume"], confidence=0.80
    )
    e5 = ExperienceEntry(
        company="B", title="Role B", start="2021-03", end="2023-06",
        sources=["resume"], confidence=0.80
    )
    years, prov = engine._strategy_computed_years_experience([e4, e5], [])
    assert years == 4.5

    # 4. Role with Present end date -> computed using run date
    # Jan 2022 - Present. Run timestamp is June 2023.
    # Jan 2022 to Jun 2023 = 18 months. 18 / 12 = 1.5 years.
    e6 = ExperienceEntry(
        company="A", title="Role A", start="2022-01", end="Present",
        sources=["resume"], confidence=0.80
    )
    years, prov = engine._strategy_computed_years_experience([e6], [])
    assert years == 1.5


def test_skills_union_with_corroboration() -> None:
    """Verifies skill deduplication, corroboration boosts, and taxonomy normalizations."""
    engine = EvidenceArbitrationEngine()
    
    # 1. "Python" from CSV + "Python" from resume -> one skill, boosted confidence, sources: ["csv", "resume"]
    c1 = SkillClaim(
        field="skills",
        raw_value="Python",
        normalized_value="Python",
        source="csv",
        source_type=SourceType.STRUCTURED,
        extraction_method=ExtractionMethod.COLUMN_MAP,
        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
        confidence=0.80,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes="",
        canonical_name="Python",
        match_type="exact",
        fuzzy_score=None
    )
    c2 = SkillClaim(
        field="skills",
        raw_value="Python",
        normalized_value="Python",
        source="resume",
        source_type=SourceType.UNSTRUCTURED,
        extraction_method=ExtractionMethod.REGEX_SECTION_BODY,
        extraction_position=ExtractionPosition.NAMED_SECTION,
        confidence=0.70,
        normalization_status=NormalizationStatus.SUCCESS,
        normalization_applied=[],
        corroborated_by=[],
        conflict_with=[],
        extraction_notes="",
        canonical_name="Python",
        match_type="exact",
        fuzzy_score=None
    )

    skills, prov = engine._strategy_union_skills([c1, c2])
    assert len(skills) == 1
    assert skills[0]["name"] == "Python"
    # Base 0.80 + 0.15 corroboration bonus = 0.95
    assert abs(skills[0]["confidence"] - 0.95) < 0.001
    assert "csv" in skills[0]["sources"]
    assert "resume" in skills[0]["sources"]
