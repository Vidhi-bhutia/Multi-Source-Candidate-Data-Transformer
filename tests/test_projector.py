"""Unit tests for runtime projection configuration behavior."""

import pytest

from app.pipeline.models import ProjectionConfig
from app.pipeline.projector import ProjectionEngine, ProjectionError


@pytest.fixture
def canonical_profile() -> dict:
    """Small canonical profile fixture with nested arrays and links."""
    return {
        "candidate_id": "abc123",
        "full_name": "Vidhi Bhutia",
        "emails": ["VIDHI@example.com"],
        "phones": ["9685856291"],
        "links": {"linkedin": "linkedin.com/in/vidhi-bhutia"},
        "years_experience": 0.9,
        "skills": [
            {"name": "py", "confidence": 0.9, "sources": ["csv"]},
            {"name": "JavaScript", "confidence": 0.7, "sources": ["resume"]},
        ],
        "experience": [
            {"company": "People Prudent", "title": "IT Intern"}
        ],
        "provenance": [{"field": "email", "source": "csv", "method": "COLUMN_MAP"}],
        "overall_confidence": 0.8,
    }


def test_custom_config_projects_nested_paths_and_strips_provenance(canonical_profile) -> None:
    """Custom config should remap, flatten list fields, normalize, and hide provenance."""
    taxonomy = {
        "python": {"canonical": "Python", "aliases": ["py"]},
        "javascript": {"canonical": "JavaScript", "aliases": ["js"]},
    }
    engine = ProjectionEngine(taxonomy)
    config = ProjectionConfig(
        fields=[
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string", "normalize": "lowercase", "required": True},
            {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
            {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"},
            {"path": "current_company", "from": "experience[0].company", "type": "string"},
            {"path": "linkedin", "from": "links.linkedin", "type": "string"},
        ],
        include_confidence=True,
        include_provenance=False,
        on_missing="null",
    )

    projected = engine.project(canonical_profile, config)

    assert projected == {
        "full_name": "Vidhi Bhutia",
        "primary_email": "vidhi@example.com",
        "phone": "+919685856291",
        "skills": ["Python", "JavaScript"],
        "current_company": "People Prudent",
        "linkedin": "linkedin.com/in/vidhi-bhutia",
        "overall_confidence": 0.8,
    }
    assert "provenance" not in projected


def test_required_missing_custom_field_raises_projection_error(canonical_profile) -> None:
    """Required custom fields should fail loudly when their source path is missing."""
    engine = ProjectionEngine()
    config = ProjectionConfig(
        fields=[
            {"path": "required_portfolio", "from": "links.portfolio[0]", "type": "string", "required": True}
        ],
        on_missing="null",
    )

    with pytest.raises(ProjectionError):
        engine.project(canonical_profile, config)


def test_object_and_array_projections_and_global_toggles(canonical_profile) -> None:
    """Test projecting full objects and lists, and verify global toggles append confidence/provenance."""
    engine = ProjectionEngine()
    
    # 1. Custom projection mapping experience (object[]) and location (object)
    # also test that include_provenance=True automatically appends provenance
    config = ProjectionConfig(
        fields=[
            {"path": "exp_history", "from": "experience", "type": "object[]"},
            {"path": "name", "from": "full_name", "type": "string"},
            {"path": "email", "from": "emails[0]", "type": "string"},
        ],
        include_confidence=False,
        include_provenance=True,
        on_missing="null",
    )
    
    projected = engine.project(canonical_profile, config)
    
    assert "exp_history" in projected
    assert isinstance(projected["exp_history"], list)
    assert projected["exp_history"][0]["company"] == "People Prudent"
    assert projected["name"] == "Vidhi Bhutia"
    
    # Provenance should be automatically appended because include_provenance=True
    assert "provenance" in projected
    assert isinstance(projected["provenance"], list)
    assert len(projected["provenance"]) > 0
    
    # overall_confidence should be missing because include_confidence=False
    assert "overall_confidence" not in projected
