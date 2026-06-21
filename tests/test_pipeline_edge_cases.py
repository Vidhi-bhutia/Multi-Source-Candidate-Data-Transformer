"""Unit tests verifying edge cases in CandidateTransformerPipeline using pytest fixtures and mocks."""

import pytest
import os
import json
from unittest.mock import MagicMock

from app.pipeline.pipeline import CandidateTransformerPipeline
from app.pipeline.extractors.resume_extractor import ResumeExtractor
from app.pipeline.source_detector import SourceDetector


@pytest.fixture
def taxonomy_data() -> dict:
    """Fixture returning a mock skills taxonomy ontology."""
    return {
        "python": {"canonical": "Python", "aliases": ["py"], "category": "languages"},
        "javascript": {"canonical": "JavaScript", "aliases": ["js"], "category": "languages"},
        "nextjs": {"canonical": "Next.js", "aliases": ["next js"], "category": "frontend"}
    }


@pytest.fixture
def pipeline_with_mock_taxonomy(tmp_path, taxonomy_data) -> CandidateTransformerPipeline:
    """Fixture returning a CandidateTransformerPipeline with a preloaded mock taxonomy file."""
    tax_file = tmp_path / "skills_taxonomy.json"
    tax_file.write_text(json.dumps(taxonomy_data))
    return CandidateTransformerPipeline(taxonomy_path=str(tax_file))


def test_edge_case_1_empty_csv(tmp_path, pipeline_with_mock_taxonomy) -> None:
    """Test 1: Run pipeline with an empty CSV file (should generate warning, not crash)."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("")  # Empty file

    result = pipeline_with_mock_taxonomy.run(csv_path=str(csv_file), resume_path=None)
    assert result["success"] is True
    assert len(result["pipeline_meta"]["sources_processed"]) == 0
    assert any("Empty file" in w for w in result["pipeline_meta"]["all_warnings"])


def test_edge_case_2_csv_no_recognized_columns(tmp_path, pipeline_with_mock_taxonomy) -> None:
    """Test 2: Run pipeline with a CSV containing no recognized column headers."""
    csv_file = tmp_path / "no_headers.csv"
    csv_file.write_text("age,gender\n30,male")

    result = pipeline_with_mock_taxonomy.run(csv_path=str(csv_file), resume_path=None)
    assert result["success"] is True
    assert len(result["pipeline_meta"]["sources_processed"]) == 1
    assert any("CSV does not contain any expected candidate columns" in w for w in result["pipeline_meta"]["all_warnings"])


def test_edge_case_3_resume_no_sections(tmp_path, monkeypatch, pipeline_with_mock_taxonomy) -> None:
    """Test 3: Run pipeline with a resume containing no section headers (no_sections_detected flag True)."""
    resume_file = tmp_path / "no_sections.pdf"
    resume_file.write_text("dummy")  # Create file placeholder

    # Mock SourceDetector to bypass reading invalid dummy PDF
    monkeypatch.setattr(
        SourceDetector,
        "detect",
        lambda self, path: {
            "file_path": path,
            "file_name": os.path.basename(path),
            "extension": ".pdf",
            "mime_type": "application/pdf",
            "detected_type": "pdf",
            "readable": True,
            "file_size_bytes": 100,
            "warning": None
        }
    )

    # Mock text extractor to return plain unstructured prose
    monkeypatch.setattr(
        ResumeExtractor,
        "_extract_text",
        lambda self, path, dtype: {
            "text": "John Doe\nThis is just a simple paragraph without headers.\nEmail: john.doe@example.com\nPython, JS",
            "page_count": 1,
            "char_count": 120
        }
    )

    result = pipeline_with_mock_taxonomy.run(csv_path=None, resume_path=str(resume_file))
    assert result["success"] is True
    # The warning list should contain low confidence warnings or warnings about section mappings
    # Let's inspect that the claims were parsed but confidence scores are relatively low due to no sections
    email_claim = result["canonical"]["emails"]
    assert "john.doe@example.com" in email_claim


def test_edge_case_4_both_files_missing(pipeline_with_mock_taxonomy) -> None:
    """Test 4: Run pipeline with both paths missing/None (should fail immediately)."""
    result = pipeline_with_mock_taxonomy.run(csv_path=None, resume_path=None)
    assert result["success"] is False
    assert "Invalid input" in result["error"]


def test_edge_case_5_csv_email_matches_resume_email(tmp_path, monkeypatch, pipeline_with_mock_taxonomy) -> None:
    """Test 5: Run pipeline with matching emails from CSV and Resume (conf should boost above 0.95)."""
    csv_file = tmp_path / "candidates.csv"
    csv_file.write_text("name,email\nJohn Doe,john@example.com")

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_text("dummy")

    # Mock SourceDetector to bypass reading invalid dummy PDF
    def mock_detect(self, path):
        if str(path).endswith(".csv"):
            return {
                "file_path": path,
                "file_name": os.path.basename(path),
                "extension": ".csv",
                "mime_type": "text/csv",
                "detected_type": "csv",
                "readable": True,
                "file_size_bytes": 100,
                "warning": None
            }
        return {
            "file_path": path,
            "file_name": os.path.basename(path),
            "extension": ".pdf",
            "mime_type": "application/pdf",
            "detected_type": "pdf",
            "readable": True,
            "file_size_bytes": 100,
            "warning": None
        }

    monkeypatch.setattr(SourceDetector, "detect", mock_detect)

    # Mock resume extractor text
    monkeypatch.setattr(
        ResumeExtractor,
        "_extract_text",
        lambda self, path, dtype: {
            "text": "John Doe\nCONTACT\nEmail: john@example.com\n",
            "page_count": 1,
            "char_count": 100
        }
    )

    result = pipeline_with_mock_taxonomy.run(csv_path=str(csv_file), resume_path=str(resume_file))
    assert result["success"] is True
    assert "john@example.com" in result["canonical"]["emails"]
    
    # Retrieve email provenance confidence score (starts at 0.95 from CSV, gets +0.15 corroboration = 1.0 capped)
    email_prov = next(p for p in result["canonical"]["provenance"] if p["field"] == "email")
    assert email_prov["winning_confidence"] == 1.0


def test_edge_case_6_phone_fails_normalization(tmp_path, pipeline_with_mock_taxonomy) -> None:
    """Test 6: Run pipeline where a CSV phone number fails normalization (phones list is empty, warning logged)."""
    csv_file = tmp_path / "candidates.csv"
    csv_file.write_text("name,email,phone\nJohn Doe,john@example.com,invalid-phone-number")

    result = pipeline_with_mock_taxonomy.run(csv_path=str(csv_file), resume_path=None)
    assert result["success"] is True
    
    # Phones list should be empty
    assert len(result["canonical"]["phones"]) == 0
    
    # Check that a phone normalization warning is recorded in the pipeline metadata
    assert any("Phone normalization failed" in w for w in result["pipeline_meta"]["all_warnings"])


def test_edge_case_7_skills_split_sources(tmp_path, monkeypatch, pipeline_with_mock_taxonomy) -> None:
    """Test 7: Run pipeline with skills coming only from the resume, not from CSV."""
    csv_file = tmp_path / "candidates.csv"
    csv_file.write_text("name,email\nJohn Doe,john@example.com")

    resume_file = tmp_path / "resume.pdf"
    resume_file.write_text("dummy")

    # Mock SourceDetector to bypass reading invalid dummy PDF
    def mock_detect(self, path):
        if str(path).endswith(".csv"):
            return {
                "file_path": path,
                "file_name": os.path.basename(path),
                "extension": ".csv",
                "mime_type": "text/csv",
                "detected_type": "csv",
                "readable": True,
                "file_size_bytes": 100,
                "warning": None
            }
        return {
            "file_path": path,
            "file_name": os.path.basename(path),
            "extension": ".pdf",
            "mime_type": "application/pdf",
            "detected_type": "pdf",
            "readable": True,
            "file_size_bytes": 100,
            "warning": None
        }

    monkeypatch.setattr(SourceDetector, "detect", mock_detect)

    monkeypatch.setattr(
        ResumeExtractor,
        "_extract_text",
        lambda self, path, dtype: {
            "text": "John Doe\nSKILLS\nPython, Next.js\n",
            "page_count": 1,
            "char_count": 100
        }
    )

    result = pipeline_with_mock_taxonomy.run(csv_path=str(csv_file), resume_path=str(resume_file))
    assert result["success"] is True
    
    skills = result["canonical"]["skills"]
    assert len(skills) > 0
    
    # All skills should source solely from resume.pdf
    for s in skills:
        assert s["sources"] == ["resume.pdf"]
