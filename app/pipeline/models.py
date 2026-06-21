"""Data models for the candidate transformation pipeline."""

from enum import Enum
from typing import Any, Optional, Union, Literal
from pydantic import BaseModel

class ExtractionMethod(str, Enum):
    """Defines the method used to extract a specific claim from the source data."""
    COLUMN_MAP = "COLUMN_MAP"
    REGEX_CONTACT_BLOCK = "REGEX_CONTACT_BLOCK"
    REGEX_SECTION_BODY = "REGEX_SECTION_BODY"
    HEURISTIC = "HEURISTIC"
    FULL_DOC_SCAN = "FULL_DOC_SCAN"
    COMPUTED = "COMPUTED"

class ExtractionPosition(str, Enum):
    """Specifies the location in the source document where the value was found."""
    EXPLICIT_FIELD = "EXPLICIT_FIELD"
    CONTACT_BLOCK = "CONTACT_BLOCK"
    NAMED_SECTION = "NAMED_SECTION"
    PROSE_BODY = "PROSE_BODY"
    FULL_DOCUMENT = "FULL_DOCUMENT"

class NormalizationStatus(str, Enum):
    """Indicates the result of the field normalization process."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PARTIAL = "PARTIAL"

class SourceType(str, Enum):
    """Categorizes the source format as structured (e.g. CSV) or unstructured (e.g. resume)."""
    STRUCTURED = "STRUCTURED"
    UNSTRUCTURED = "UNSTRUCTURED"

class Claim(BaseModel):
    """Represents an individual evidence claim for a field extracted from a specific source."""
    field: str
    raw_value: Any
    normalized_value: Any
    source: str
    source_type: SourceType
    extraction_method: ExtractionMethod
    extraction_position: ExtractionPosition
    confidence: float
    normalization_status: NormalizationStatus
    normalization_applied: list[str]
    corroborated_by: list[str]
    conflict_with: list[str]
    extraction_notes: str

class SkillClaim(Claim):
    """Extends Claim with metadata specific to taxonomical skill matches."""
    canonical_name: str
    match_type: str
    fuzzy_score: Optional[float] = None

class ExperienceEntry(BaseModel):
    """Represents a work experience epoch reconstructed from source evidence."""
    company: Optional[str] = None
    title: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    summary: Optional[str] = None
    concurrent: bool = False
    sources: list[str]
    confidence: float

class EducationEntry(BaseModel):
    """Represents an educational enrollment history reconstructed from source evidence."""
    institution: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[int] = None
    sources: list[str]
    confidence: float

class ProvenanceRecord(BaseModel):
    """Represents the audit trail and resolution history for a specific canonical field."""
    field: str
    winning_value: Any
    winning_source: str
    winning_method: str
    winning_confidence: float
    resolution_strategy: str
    all_claims: list[dict[str, Any]]
    conflict_detected: bool
    transformation_applied: list[str]

class CanonicalCandidate(BaseModel):
    """Represents the final, unified, and arbitrated candidate profile representation."""
    candidate_id: str
    full_name: Optional[str] = None
    emails: list[str]
    phones: list[str]
    location: dict[str, Any]
    links: dict[str, Any]
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[dict[str, Any]]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    provenance: list[ProvenanceRecord]
    overall_confidence: float
    pipeline_run_timestamp: str
    sources_processed: list[str]
    warnings: list[str]

class ProjectionConfig(BaseModel):
    """Defines configuration parameters for filtering and transforming canonical outputs."""
    fields: list[dict[str, Any]]
    include_confidence: bool = True
    include_provenance: bool = True
    on_missing: Literal["null", "omit", "error"] = "null"

class ValidationResult(BaseModel):
    """Encapsulates the final validity status and structural diagnostics of a candidate."""
    valid: bool
    errors: list[dict[str, Any]]
    warnings: list[str]
    projected_output: Optional[dict[str, Any]] = None
