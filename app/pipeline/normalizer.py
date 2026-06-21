"""Normalizer component to validate, clean, and standardize extracted candidate claims."""

import re
import logging
import phonenumbers

from app.pipeline.models import (
    Claim,
    SkillClaim,
    NormalizationStatus
)

# Setup logger
logger = logging.getLogger(__name__)

# Months mapping for date formatting
MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12"
}

# Regex matching months pattern
MONTHS_PATTERN = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'

# ISO-3166-alpha-2 country mappings
COUNTRY_MAP = {
    "india": "IN",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "germany": "DE",
    "canada": "CA",
    "australia": "AU",
    "singapore": "SG"
}


class Normalizer:
    """Standardizes data claims to target formats (e.g. E.164 phone formats, ISO country codes)."""

    def __init__(self, taxonomy: dict = None) -> None:
        """Initializes the Normalizer instance with a skills taxonomy dictionary."""
        self.taxonomy = taxonomy or {}

    def _normalize_month(self, m_str: str) -> str:
        """Translates month name string to a two-digit month representation ('01'-'12')."""
        return MONTH_MAP.get(m_str.lower().strip(), "01")

    def _normalize_phone(self, raw: str) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Standardizes a phone string using phonenumbers library and formats to E.164."""
        num = None
        # Heuristic: if the raw string matches a US format pattern, evaluate US region first
        try_us_first = False
        if re.search(r'^\s*\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}', raw):
            try_us_first = True

        regions = ["US", "IN"] if try_us_first else ["IN", "US"]

        for region in regions:
            try:
                parsed = phonenumbers.parse(raw, region)
                if phonenumbers.is_valid_number(parsed):
                    num = parsed
                    break
            except Exception:
                pass

        # Parse without region hint if both explicit checks fail
        if not num:
            try:
                parsed = phonenumbers.parse(raw, None)
                if phonenumbers.is_valid_number(parsed):
                    num = parsed
            except Exception:
                pass

        if num:
            formatted = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
            return formatted, NormalizationStatus.SUCCESS, ["parsed_with_phonenumbers", "formatted_e164"], None
        else:
            note = f"Phone normalization failed: {raw}. Stored as null per policy."
            return None, NormalizationStatus.FAILED, [], note

    def _normalize_email(self, raw: str) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Cleans and validates an email address against standard formatting rules."""
        raw_clean = raw.strip()
        transformations = []
        note = None

        # Check for multiple emails inside a single string
        if ',' in raw_clean or ';' in raw_clean:
            parts = re.split(r'[,;]+', raw_clean)
            first_valid = None
            for part in parts:
                p_clean = part.strip().lower()
                if re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', p_clean):
                    first_valid = p_clean
                    break
            
            if first_valid:
                note = f"Multiple emails detected. Selected first valid email: {first_valid}"
                transformations.append("split_multiple_emails")
                return first_valid, NormalizationStatus.SUCCESS, transformations, note
            else:
                note = f"Multiple emails detected but none were valid: {raw}"
                return None, NormalizationStatus.FAILED, [], note

        email = raw_clean.lower()
        if re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', email):
            return email, NormalizationStatus.SUCCESS, ["lowercased", "stripped"], None
        else:
            return None, NormalizationStatus.FAILED, [], None

    def _normalize_date(self, raw: str) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Normalizes date representations to the target format YYYY-MM."""
        raw_clean = raw.strip()

        # 1. Present indicators
        if raw_clean.lower() in {"present", "current", "now", "ongoing", "till date"}:
            return None, NormalizationStatus.NOT_APPLICABLE, [], "end_date_is_present"

        # 2. YYYY-MM format match
        m_ym = re.match(r'^\s*(\d{4})\-(\d{2})\s*$', raw_clean)
        if m_ym:
            return f"{m_ym.group(1)}-{m_ym.group(2)}", NormalizationStatus.SUCCESS, ["parsed_yyyy_mm"], None

        # 3. Month YYYY format match
        m_my = re.match(rf'^\s*({MONTHS_PATTERN})\s+(\d{{4}})\s*$', raw_clean, re.IGNORECASE)
        if m_my:
            year = m_my.group(2)
            month = self._normalize_month(m_my.group(1))
            return f"{year}-{month}", NormalizationStatus.SUCCESS, ["parsed_month_year"], None

        # 4. MM/YYYY format match
        m_my_slash = re.match(r'^\s*(\d{1,2})/(\d{4})\s*$', raw_clean)
        if m_my_slash:
            year = m_my_slash.group(2)
            month = m_my_slash.group(1).zfill(2)
            return f"{year}-{month}", NormalizationStatus.SUCCESS, ["parsed_slash_date"], None

        # 5. YYYY format match (Partial)
        m_y = re.match(r'^\s*(\d{4})\s*$', raw_clean)
        if m_y:
            year = m_y.group(1)
            return f"{year}-01", NormalizationStatus.PARTIAL, ["defaulted_to_month_01"], "Only year available, defaulted to month 01"

        return None, NormalizationStatus.FAILED, [], f"Date normalization failed for value: {raw}"

    def _normalize_country(self, raw: str) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Standardizes a country name to its ISO-3166-alpha-2 format."""
        raw_clean = raw.strip().lower()
        if raw_clean in COUNTRY_MAP:
            return COUNTRY_MAP[raw_clean], NormalizationStatus.SUCCESS, ["iso3166_mapping"], None
        return None, NormalizationStatus.FAILED, [], f"Country normalization failed for value: {raw}"

    def _normalize_name(self, raw: str) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Cleans name components, title-cases, and corrects 'Last, First' inversions."""
        raw_clean = raw.strip()
        transformations = []

        # Last, First name format swap check
        if ',' in raw_clean:
            parts = [p.strip() for p in raw_clean.split(',', 1)]
            if len(parts) == 2 and ' ' not in parts[0]:
                raw_clean = f"{parts[1]} {parts[0]}"
                transformations.append("swapped_last_first")

        raw_clean = raw_clean.title()
        transformations.append("title_cased")

        # Collapse excess internal spacing
        raw_clean = " ".join(raw_clean.split())
        transformations.append("removed_internal_whitespace")

        if not raw_clean:
            return None, NormalizationStatus.FAILED, [], "Name is empty"

        return raw_clean, NormalizationStatus.SUCCESS, transformations, None

    def _normalize_skill(self, raw: str, taxonomy: dict, match_type: str = "unverified", canonical: str = None) -> tuple[str | None, NormalizationStatus, list[str], str | None]:
        """Aligns skill tokens against the canonical naming system in the taxonomy."""
        raw_lower = raw.lower().strip()
        # Find exact or alias matches in taxonomy
        for key, entry in taxonomy.items():
            if raw_lower == key or raw_lower in [a.lower() for a in entry.get("aliases", [])]:
                return entry["canonical"], NormalizationStatus.SUCCESS, ["taxonomy_exact_or_alias_match"], None

        # Return fuzzy match results if pre-determined
        if match_type == "fuzzy" and canonical:
            return canonical, NormalizationStatus.SUCCESS, ["taxonomy_fuzzy_match"], None

        # Return title-cased unverified skills
        return raw.title(), NormalizationStatus.PARTIAL, ["title_cased_fallback"], "Skill not in taxonomy, kept as-is"

    def normalize(self, claims: list[Claim]) -> list[Claim]:
        """Routes claims to their target field normalizers and yields a new normalized claims list."""
        normalized_claims: list[Claim] = []

        for claim in claims:
            # Use model_copy to preserve Claim/SkillClaim subclass identity
            new_claim = claim.model_copy()

            norm_val = None
            status = NormalizationStatus.NOT_APPLICABLE
            transformations = []
            note = None

            # Route by claim field name
            if claim.field == "email":
                norm_val, status, transformations, note = self._normalize_email(claim.raw_value)
            elif claim.field == "phone":
                norm_val, status, transformations, note = self._normalize_phone(claim.raw_value)
            elif claim.field == "full_name":
                norm_val, status, transformations, note = self._normalize_name(claim.raw_value)
            elif claim.field in ["start", "end"]:
                norm_val, status, transformations, note = self._normalize_date(claim.raw_value)
            elif claim.field == "location" and isinstance(claim.raw_value, dict):
                # Standardize location country
                loc_copy = dict(claim.raw_value)
                country_raw = loc_copy.get("country", "")
                if country_raw:
                    c_val, c_status, c_trans, c_note = self._normalize_country(country_raw)
                    if c_status == NormalizationStatus.SUCCESS:
                        loc_copy["country"] = c_val
                        transformations.extend(c_trans)
                    else:
                        note = c_note
                norm_val = loc_copy
                status = NormalizationStatus.SUCCESS
            elif claim.field == "skills":
                match_type = getattr(claim, "match_type", "unverified")
                canonical = getattr(claim, "canonical_name", None)
                norm_val, status, transformations, note = self._normalize_skill(
                    claim.raw_value,
                    self.taxonomy,
                    match_type=match_type,
                    canonical=canonical
                )
            elif claim.field == "experience" and isinstance(claim.raw_value, list):
                # Normalize dates inside nested ExperienceEntry objects
                norm_val = []
                for entry in claim.raw_value:
                    new_entry = entry.model_copy()
                    if new_entry.start:
                        d_val, d_status, _, _ = self._normalize_date(new_entry.start)
                        if d_status != NormalizationStatus.FAILED:
                            new_entry.start = d_val
                    if new_entry.end:
                        d_val, d_status, _, _ = self._normalize_date(new_entry.end)
                        if d_status != NormalizationStatus.FAILED:
                            new_entry.end = d_val
                    norm_val.append(new_entry)
                status = NormalizationStatus.SUCCESS
                transformations = ["normalized_experience_dates"]
            elif claim.field == "education" and isinstance(claim.raw_value, list):
                norm_val = claim.raw_value
                status = NormalizationStatus.SUCCESS
                transformations = []
            else:
                norm_val = claim.raw_value
                status = NormalizationStatus.NOT_APPLICABLE
                transformations = []

            # Populate fields on new claim instance
            new_claim.normalized_value = norm_val
            new_claim.normalization_status = status
            new_claim.normalization_applied = transformations

            if note:
                if new_claim.extraction_notes:
                    new_claim.extraction_notes += f" | Normalization notes: {note}"
                else:
                    new_claim.extraction_notes = note

            normalized_claims.append(new_claim)

        return normalized_claims
