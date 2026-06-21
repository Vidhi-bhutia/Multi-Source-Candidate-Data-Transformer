"""Canonical Candidate Builder module to construct and serialize the final unified profile."""

import hashlib
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any

from app.pipeline.models import (
    CanonicalCandidate,
    ProvenanceRecord,
    ExperienceEntry,
    EducationEntry
)

# Setup logger
logger = logging.getLogger(__name__)


class CanonicalCandidateBuilder:
    """Assembles the final CanonicalCandidate profile with full audit provenance and JSON serialization."""

    def __init__(self) -> None:
        """Initializes the CanonicalCandidateBuilder instance."""
        pass

    def build(self, arbitrated_values: dict, provenance: list[ProvenanceRecord], sources_processed: list[str], warnings: list[str]) -> CanonicalCandidate:
        """Assembles and returns a populated CanonicalCandidate model instance."""
        local_warnings = list(warnings)

        # 1. CANDIDATE ID GENERATION (SHA-256 of normalized email, name, or UUID)
        emails = arbitrated_values.get("emails", [])
        if emails and len(emails) > 0:
            primary_email = str(emails[0]).lower().strip()
            candidate_id = hashlib.sha256(primary_email.encode("utf-8")).hexdigest()
        else:
            full_name = arbitrated_values.get("full_name")
            if full_name:
                name_clean = str(full_name).lower().strip()
                candidate_id = hashlib.sha256(name_clean.encode("utf-8")).hexdigest()
                local_warnings.append("No email address found. Generated candidate_id using full_name hash fallback.")
            else:
                random_uuid = str(uuid4())
                candidate_id = hashlib.sha256(random_uuid.encode("utf-8")).hexdigest()
                local_warnings.append("No email or name found. Generated candidate_id using random UUID hash fallback.")

        # 2. Extract and format fields
        full_name = arbitrated_values.get("full_name")
        
        # Ensure emails and phones are list structures
        emails_list = list(emails) if isinstance(emails, (list, tuple)) else []
        phones = arbitrated_values.get("phones", [])
        phones_list = list(phones) if isinstance(phones, (list, tuple)) else []

        # Location fallback
        location = arbitrated_values.get("location", {"city": None, "region": None, "country": None})

        # Links dictionary consolidation
        links = arbitrated_values.get("links")
        if not links:
            links = {
                "linkedin": arbitrated_values.get("linkedin_url"),
                "github": arbitrated_values.get("github_url"),
                "portfolio": arbitrated_values.get("portfolio_url"),
                "other": []
            }

        headline = arbitrated_values.get("headline")
        years_experience = arbitrated_values.get("years_experience")
        skills = arbitrated_values.get("skills", [])
        experience = arbitrated_values.get("experience", [])
        education = arbitrated_values.get("education", [])
        overall_confidence = arbitrated_values.get("overall_confidence", 0.0)

        # UTC timestamp representation in ISO Zulu format
        run_timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Instantiate Pydantic model
        return CanonicalCandidate(
            candidate_id=candidate_id,
            full_name=full_name,
            emails=emails_list,
            phones=phones_list,
            location=location,
            links=links,
            headline=headline,
            years_experience=years_experience,
            skills=skills,
            experience=experience,
            education=education,
            provenance=provenance,
            overall_confidence=overall_confidence,
            pipeline_run_timestamp=run_timestamp,
            sources_processed=sources_processed,
            warnings=local_warnings
        )

    def to_dict(self, canonical: CanonicalCandidate) -> dict:
        """Converts the CanonicalCandidate Pydantic model into a plain serializable dict representation."""
        # Pydantic v2 model_dump with mode="json" automatically serializes Enums, dates, and nested types
        try:
            return canonical.model_dump(mode="json")
        except Exception as e:
            logger.error(f"Pydantic model_dump failed, falling back to manual serialization: {e}")
            # Manual fallback routing if v2 json dump throws exceptions
            return self._manual_dump(canonical)

    def _manual_dump(self, val: Any) -> Any:
        """Fallback recursive serializer for converting nested models to standard python primitives."""
        # Convert list structures
        if isinstance(val, list):
            return [self._manual_dump(item) for item in val]
        # Convert dict structures
        elif isinstance(val, dict):
            return {k: self._manual_dump(v) for k, v in val.items()}
        # Convert Pydantic structures
        elif hasattr(val, "model_dump"):
            return self._manual_dump(val.model_dump())
        # Convert Enum types
        elif hasattr(val, "value"):
            return val.value
        # Default primitive return
        return val
