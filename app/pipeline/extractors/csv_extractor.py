"""CSV extractor component to parse candidate data from structured CSV inputs and generate claims."""

import os
import csv
import io
import logging
import chardet

from app.pipeline.models import (
    Claim,
    ExtractionMethod,
    ExtractionPosition,
    SourceType,
    NormalizationStatus
)

# Set up logger
logger = logging.getLogger(__name__)

# Column names mapping to canonical field names
COLUMN_MAP = {
    "name": "full_name",
    "email": "email",
    "phone": "phone",
    "current_company": "current_company",
    "title": "headline"
}

# Confidence scores associated with specific fields in a structured source
CONFIDENCE_MAP = {
    "email": 0.95,
    "phone": 0.90,
    "full_name": 0.85,
    "headline": 0.80,
    "current_company": 0.80
}

# Values that represent null or empty mappings in structured sheets
SKIP_VALUES = {"n/a", "na", "null", "none", "-"}


class CSVExtractor:
    """Extracts raw candidate data from CSV sheets and registers them as individual claims."""

    def __init__(self) -> None:
        """Initializes the CSVExtractor instance and sets up warnings collection."""
        self.warnings: list[str] = []

    def get_warnings(self) -> list[str]:
        """Returns the warnings accumulated during the extraction process."""
        return self.warnings

    def _read_file_with_encoding(self, file_path: str) -> str:
        """Attempts to decode and read the CSV content with multiple encoding fallbacks."""
        # Try UTF-8-sig first to gracefully handle and strip the Byte Order Mark (BOM)
        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                return f.read()
        except UnicodeDecodeError:
            logger.debug(f"UTF-8-sig decoding failed for {file_path}. Trying latin-1.")

        # Fall back to latin-1
        try:
            with open(file_path, mode='r', encoding='latin-1') as f:
                return f.read()
        except UnicodeDecodeError:
            logger.debug(f"Latin-1 decoding failed for {file_path}. Trying cp1252.")

        # Fall back to cp1252
        try:
            with open(file_path, mode='r', encoding='cp1252') as f:
                return f.read()
        except UnicodeDecodeError:
            logger.debug(f"Cp1252 decoding failed for {file_path}. Using chardet as fallback.")

        # Fall back to chardet detection
        try:
            with open(file_path, mode='rb') as f:
                raw_data = f.read()
            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding') or 'utf-8'
            return raw_data.decode(encoding, errors='ignore')
        except Exception as e:
            # Absolute fallback: ignore bad bytes to ensure pipeline doesn't crash
            logger.error(f"All encoding detections failed for {file_path}: {e}. Reading as raw UTF-8 ignoring errors.")
            with open(file_path, mode='r', encoding='utf-8', errors='ignore') as f:
                return f.read()

    def extract(self, file_path: str) -> list[Claim]:
        """Reads a CSV file and builds a flat list of claims for populated fields."""
        # Reset warnings for the new extraction run
        self.warnings = []
        claims: list[Claim] = []

        if not os.path.exists(file_path):
            self.warnings.append(f"File not found: {file_path}")
            return []

        # Read the file using the robust encoding lookup
        file_content = self._read_file_with_encoding(file_path)
        if not file_content.strip():
            self.warnings.append("CSV file is empty.")
            return []

        # Parse CSV strings via in-memory stream
        f = io.StringIO(file_content)
        reader = csv.reader(f)

        try:
            # Extract header and verify column structure
            headers = next(reader, None)
            if not headers:
                self.warnings.append("CSV file has no header row.")
                return []
        except Exception as e:
            logger.error(f"Error parsing headers for {file_path}: {e}")
            self.warnings.append(f"Failed to parse CSV headers: {str(e)}")
            return []

        # Store headers as originally formatted for claims documentation
        original_headers = headers
        num_columns = len(headers)

        # Normalize column header values: lowercase, stripped, spaces replaced with underscores
        normalized_headers = [h.strip().lower().replace(" ", "_") for h in headers]

        # Process each data row, tracking row index starting at row 2 (row 1 is header)
        for row_idx, row in enumerate(reader, start=2):
            # Check for malformed rows where column count deviates from header count
            if len(row) != num_columns:
                self.warnings.append(
                    f"Row {row_idx} is malformed: expected {num_columns} columns, got {len(row)} columns. Row skipped."
                )
                continue

            for col_idx, cell_value in enumerate(row):
                normalized_col = normalized_headers[col_idx]
                original_col = original_headers[col_idx]

                # Check if the column name matches any target canonical mapping
                if normalized_col in COLUMN_MAP:
                    canonical_field = COLUMN_MAP[normalized_col]
                    raw_value = cell_value.strip()

                    # Skip empty cell entries
                    if not raw_value:
                        continue

                    # Skip cells representing placeholders or null indicators (case-insensitive)
                    if raw_value.lower() in SKIP_VALUES:
                        continue

                    # Resolve preset field confidence weights
                    confidence = CONFIDENCE_MAP.get(canonical_field, 0.5)

                    # Build Claim object
                    claim = Claim(
                        field=canonical_field,
                        raw_value=raw_value,
                        normalized_value=None,
                        source=os.path.basename(file_path),
                        source_type=SourceType.STRUCTURED,
                        extraction_method=ExtractionMethod.COLUMN_MAP,
                        extraction_position=ExtractionPosition.EXPLICIT_FIELD,
                        confidence=confidence,
                        normalization_status=NormalizationStatus.NOT_APPLICABLE,
                        normalization_applied=[],
                        corroborated_by=[],
                        conflict_with=[],
                        extraction_notes=f"Extracted from CSV column '{original_col}'"
                    )
                    claims.append(claim)

        return claims
