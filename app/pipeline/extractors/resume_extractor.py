"""Resume extractor component to parse candidate details from unstructured PDF, DOCX, and image resumes."""

import os
import re
import logging
import unicodedata

from app.pipeline.models import (
    Claim,
    SkillClaim,
    ExperienceEntry,
    EducationEntry,
    ExtractionMethod,
    ExtractionPosition,
    SourceType,
    NormalizationStatus
)

# Setup logging
logger = logging.getLogger(__name__)

# Known headers mapping to canonical sections
KEYWORD_MAP = {
    "experience": "EXPERIENCE",
    "work experience": "EXPERIENCE",
    "work history": "EXPERIENCE",
    "education": "EDUCATION",
    "academic": "EDUCATION",
    "skills": "SKILLS",
    "technical skills": "SKILLS",
    "projects": "PROJECTS",
    "summary": "SUMMARY",
    "objective": "OBJECTIVE",
    "certifications": "CERTIFICATIONS",
    "publications": "PUBLICATIONS",
    "awards": "AWARDS",
    "contact": "CONTACT",
    "links": "LINKS",
    "open source": "OPEN_SOURCE"
}

# List of keywords for regex matching section headers
KEYWORDS = set(KEYWORD_MAP.keys())

# Non-name words that shouldn't match Name Heuristic
NON_NAME_WORDS = {"resume", "cv", "curriculum", "email", "phone", "mobile", "page", "address", "links", "contact"}

# Months mapping for date range parsing
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

# Regex string for months pattern
MONTHS_PATTERN = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'

# Indian cities list for location parsing
INDIAN_CITIES = ["Mumbai", "Delhi", "Bengaluru", "Bangalore", "Pune", "Chennai", "Hyderabad", "Kolkata", "Gurgaon", "Noida", "Ahmedabad"]

# Degree keywords for education block parsing
DEGREE_KEYWORDS = ["B.Tech", "B.E.", "B.Sc", "Bachelor", "M.Tech", "M.Sc", "Master", "MBA", "PhD", "Ph.D", "Diploma", "Class XII", "Class X", "12th", "10th", "HSC", "SSC", "CBSE", "ICSE"]

# School indicators for education block parsing
INSTITUTION_INDICATORS = ["Institute", "University", "School", "Vidyalaya", "College", "Academy"]


class ResumeExtractor:
    """Extracts claims from unstructured PDF, DOCX, and scanned PDF resumes using evidence-based methods."""

    def __init__(self) -> None:
        """Initializes the ResumeExtractor instance."""
        self.warnings: list[str] = []
        self.near_empty = False
        self.no_sections_detected = False

    def get_warnings(self) -> list[str]:
        """Returns the list of non-fatal warnings encountered during execution."""
        return self.warnings

    def _adjust_confidence(self, conf: float) -> float:
        """Applies pipeline confidence penalties based on file emptiness or missing sections."""
        if self.no_sections_detected:
            # Deduct 0.15 confidence if resume has no clean section structure
            conf -= 0.15
        if self.near_empty:
            # Multiply confidence by 0.3 if character count is critically low (< 50)
            conf *= 0.3
        # Keep confidence clipped to standard probability bounds [0.0, 1.0]
        return max(0.0, min(1.0, conf))

    def _extract_text(self, file_path: str, detected_type: str) -> dict:
        """Part 1: Extracts text content page by page using type-specific libraries."""
        if detected_type == "pdf":
            try:
                import pdfplumber
                text = ""
                page_count = 0
                with pdfplumber.open(file_path) as pdf:
                    page_count = len(pdf.pages)
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return {
                    "text": text,
                    "method": "pdfplumber",
                    "page_count": page_count,
                    "char_count": len(text)
                }
            except Exception as e:
                logger.error(f"pdfplumber text extraction failed for {file_path}: {e}")
                self.warnings.append(f"pdfplumber failed: {str(e)}")
                # Try fallback to empty text to prevent pipeline crash
                return {"text": "", "method": "pdfplumber_failed", "page_count": 0, "char_count": 0}

        elif detected_type == "image_pdf":
            try:
                import pdfplumber
                import pytesseract
                # Test connection to tesseract binary
                pytesseract.get_tesseract_version()

                text = ""
                page_count = 0
                with pdfplumber.open(file_path) as pdf:
                    page_count = len(pdf.pages)
                    for page in pdf.pages:
                        # Render the PDF page to a 150 DPI PIL image
                        pil_img = page.to_image(resolution=150).original
                        page_text = pytesseract.image_to_string(pil_img)
                        if page_text:
                            text += page_text + "\n"
                return {
                    "text": text,
                    "method": "ocr_tesseract",
                    "page_count": page_count,
                    "char_count": len(text)
                }
            except Exception as e:
                logger.error(f"pytesseract OCR text extraction failed for {file_path}: {e}")
                warn_msg = "OCR failed. Install tesseract-ocr system package."
                self.warnings.append(warn_msg)
                return {
                    "text": "",
                    "method": "ocr_failed",
                    "page_count": 0,
                    "char_count": 0,
                    "warning": warn_msg
                }

        elif detected_type == "docx":
            try:
                import docx
                doc = docx.Document(file_path)
                # Combine all paragraph texts using newlines
                paragraphs = [p.text for p in doc.paragraphs]
                text = "\n".join(paragraphs)
                return {
                    "text": text,
                    "method": "python_docx",
                    "page_count": None,
                    "char_count": len(text)
                }
            except Exception as e:
                logger.error(f"python-docx text extraction failed for {file_path}: {e}")
                self.warnings.append(f"python-docx failed: {str(e)}")
                return {"text": "", "method": "python_docx_failed", "page_count": None, "char_count": 0}

        # Catch-all fallback
        return {"text": "", "method": "unknown", "page_count": None, "char_count": 0}

    def _clean_text(self, text: str) -> str:
        """Part 2: Cleans file text formatting while preserving character content."""
        # 1. Remove null bytes and non-printable characters (keep newlines and tabs)
        cleaned_chars = []
        for char in text:
            if char in ('\n', '\t'):
                cleaned_chars.append(char)
            elif char == '\0':
                continue
            elif char.isprintable():
                cleaned_chars.append(char)
        
        cleaned_text = "".join(cleaned_chars)

        # 2. Normalize to NFC Unicode Form
        cleaned_text = unicodedata.normalize('NFC', cleaned_text)

        # 3. Collapse multiple consecutive blank lines and strip each line
        lines = cleaned_text.split('\n')
        cleaned_lines = []
        last_was_blank = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not last_was_blank:
                    cleaned_lines.append("")
                    last_was_blank = True
            else:
                cleaned_lines.append(stripped)
                last_was_blank = False

        return "\n".join(cleaned_lines).strip()

    def _detect_sections(self, text: str) -> dict:
        """Part 3: Detects section boundaries in text based on header pattern matching."""
        lines = text.split('\n')
        sections = {}

        # 1. Store first 15 lines in CONTACT_BLOCK
        sections["CONTACT_BLOCK"] = "\n".join(lines[:15])

        # 2. Find indices of all section header lines
        header_indices = []
        for i, line in enumerate(lines):
            cleaned_line = line.strip()
            if not cleaned_line:
                continue

            header_check = cleaned_line.rstrip(':').strip()
            # Header must have characters to prevent lines like "---" from matching
            is_all_caps = header_check.isupper() and any(c.isalpha() for c in header_check)
            is_keyword = header_check.lower() in KEYWORDS

            if (is_all_caps or is_keyword) and len(header_check) < 50:
                # Check lookahead for non-empty content
                has_next_content = False
                for next_line in lines[i+1:]:
                    if next_line.strip():
                        has_next_content = True
                        break

                if has_next_content:
                    header_indices.append((i, header_check))

        # 3. If no sections detected, apply warning flags
        if not header_indices:
            self.no_sections_detected = True
            sections["FULL_DOCUMENT"] = text
            return sections

        self.no_sections_detected = False

        # 4. Partition text into body regions
        for k in range(len(header_indices)):
            start_idx, header_text = header_indices[k]
            end_idx = header_indices[k+1][0] if k + 1 < len(header_indices) else len(lines)

            section_lines = lines[start_idx + 1:end_idx]
            section_body = "\n".join(section_lines).strip()

            # Map section name using canonical KEYWORD_MAP
            normalized_hdr = header_text.lower().strip()
            canonical_key = KEYWORD_MAP.get(normalized_hdr, header_text.upper())

            # Append content if same section key occurs multiple times
            if canonical_key in sections:
                sections[canonical_key] += "\n" + section_body
            else:
                sections[canonical_key] = section_body

        return sections

    def _extract_contact(self, contact_text: str, source_name: str) -> list[Claim]:
        """Part 4: Extracts contact claims (Name, Email, Phone, Links, Location) from top context block."""
        claims = []
        lines = contact_text.split('\n')

        # 1. EMAIL EXTRACTION (Multiple allowed)
        email_pattern = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
        for email_match in re.finditer(email_pattern, contact_text):
            email_val = email_match.group(0).strip()
            # Base confidence: 0.70 (source) * 0.95 (method) * 1.00 (position) = 0.665
            claims.append(Claim(
                field="email",
                raw_value=email_val,
                normalized_value=None,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                extraction_position=ExtractionPosition.CONTACT_BLOCK,
                confidence=self._adjust_confidence(0.665),
                normalization_status=NormalizationStatus.NOT_APPLICABLE,
                normalization_applied=[],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes="Extracted from contact block using standard email regex."
            ))

        # 2. PHONE EXTRACTION (Multiple allowed, first match per line)
        phone_patterns = [
            r'\+\d{1,3}[\s\-]?\d{4,14}',            # Pattern 1: E.164
            r'[6-9]\d{9}',                           # Pattern 2: Indian Format
            r'\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}', # Pattern 3: US Format
            r'\d[\d\s\-\.\(\)]{7,15}\d'              # Pattern 4: Generic
        ]
        for line in lines:
            for pattern in phone_patterns:
                phone_match = re.search(pattern, line)
                if phone_match:
                    phone_val = phone_match.group(0).strip()
                    # Skip if the match is a date range or a simple year/number
                    if re.match(r'^\d{4}\s*[\-–—]\s*\d{4}$', phone_val) or re.match(r'^\d{4}$', phone_val):
                        continue
                    # Base confidence: 0.70 * 0.95 * 1.00 = 0.665
                    claims.append(Claim(
                        field="phone",
                        raw_value=phone_val,
                        normalized_value=None,
                        source=source_name,
                        source_type=SourceType.UNSTRUCTURED,
                        extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                        extraction_position=ExtractionPosition.CONTACT_BLOCK,
                        confidence=self._adjust_confidence(0.665),
                        normalization_status=NormalizationStatus.NOT_APPLICABLE,
                        normalization_applied=[],
                        corroborated_by=[],
                        conflict_with=[],
                        extraction_notes=f"Extracted phone pattern from line: {line.strip()}"
                    ))
                    break  # Stop evaluating remaining patterns for this line

        # 3. NAME HEURISTIC EXTRACTION (First match in top 5 lines)
        for line in lines[:5]:
            line_clean = line.strip()
            if not line_clean:
                continue

            tokens = line_clean.split()
            # Condition A: 2-4 tokens
            if not (2 <= len(tokens) <= 4):
                continue
            # Condition B: No digits
            if any(c.isdigit() for c in line_clean):
                continue
            # Condition C: No @ symbols
            if '@' in line_clean:
                continue
            # Condition D: Not a URL
            lower_line = line_clean.lower()
            if any(indicator in lower_line for indicator in ["http", "www", "github", "linkedin", ".com", ".org", ".in"]):
                continue
            # Condition E: No non-name keywords
            if any(token.lower() in NON_NAME_WORDS for token in tokens):
                continue

            # Condition F: Capitalization check (tokens start with uppercase or are single letters)
            all_capitalized = True
            for token in tokens:
                t_clean = token.rstrip('.,')
                if not t_clean:
                    all_capitalized = False
                    break
                if not (t_clean[0].isupper() or (len(t_clean) == 1 and t_clean.isupper())):
                    all_capitalized = False
                    break

            if all_capitalized:
                # Name found; register name claim
                # Base confidence: 0.70 (source) * 0.70 (method) * 1.00 (position) = 0.49
                claims.append(Claim(
                    field="full_name",
                    raw_value=line_clean,
                    normalized_value=None,
                    source=source_name,
                    source_type=SourceType.UNSTRUCTURED,
                    extraction_method=ExtractionMethod.HEURISTIC,
                    extraction_position=ExtractionPosition.CONTACT_BLOCK,
                    confidence=self._adjust_confidence(0.49),
                    normalization_status=NormalizationStatus.NOT_APPLICABLE,
                    normalization_applied=[],
                    corroborated_by=[],
                    conflict_with=[],
                    extraction_notes="Name inferred from first title-cased line in contact block"
                ))
                break  # Only take the first matching line

        # 4. LINKS EXTRACTION (LinkedIn, GitHub, Portfolio)
        # LinkedIn
        for link_match in re.finditer(r'linkedin\.com/in/[\w\-]+', contact_text, re.IGNORECASE):
            claims.append(Claim(
                field="linkedin_url",
                raw_value=link_match.group(0).strip(),
                normalized_value=None,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                extraction_position=ExtractionPosition.CONTACT_BLOCK,
                confidence=self._adjust_confidence(0.665),
                normalization_status=NormalizationStatus.NOT_APPLICABLE,
                normalization_applied=[],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes="LinkedIn profile link extracted from contact block."
            ))

        # GitHub
        for link_match in re.finditer(r'github\.com/[\w\-]+', contact_text, re.IGNORECASE):
            claims.append(Claim(
                field="github_url",
                raw_value=link_match.group(0).strip(),
                normalized_value=None,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                extraction_position=ExtractionPosition.CONTACT_BLOCK,
                confidence=self._adjust_confidence(0.665),
                normalization_status=NormalizationStatus.NOT_APPLICABLE,
                normalization_applied=[],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes="GitHub profile link extracted from contact block."
            ))

        # Portfolio (URLs excluding linkedin/github)
        for link_match in re.finditer(r'https?://(?!linkedin|github)[\w\-\.]+\.[a-z]{2,}', contact_text, re.IGNORECASE):
            claims.append(Claim(
                field="portfolio_url",
                raw_value=link_match.group(0).strip(),
                normalized_value=None,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                extraction_position=ExtractionPosition.CONTACT_BLOCK,
                confidence=self._adjust_confidence(0.665),
                normalization_status=NormalizationStatus.NOT_APPLICABLE,
                normalization_applied=[],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes="Portfolio/website link extracted from contact block."
            ))

        # 5. LOCATION EXTRACTION
        # City State pattern (e.g. Mumbai, Maharashtra)
        city_regex = r'\b(' + '|'.join(INDIAN_CITIES) + r')\b(?:,\s*([a-zA-Z\s]{2,20}))?(?:,\s*India)?'
        loc_match = re.search(city_regex, contact_text, re.IGNORECASE)
        if loc_match:
            city_raw = loc_match.group(1)
            state_raw = loc_match.group(2)
            
            # Normalize region if it matches India
            region = state_raw.strip() if state_raw else None
            if region and region.lower() in ["india", "in"]:
                region = None

            # Get title-cased city name from list
            city_canonical = next(c for c in INDIAN_CITIES if c.lower() == city_raw.lower())

            # Base confidence: 0.70 (source) * 0.80 (method) * 1.00 (position) = 0.56
            claims.append(Claim(
                field="location",
                raw_value={"city": city_canonical, "region": region, "country": "IN"},
                normalized_value=None,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=ExtractionMethod.REGEX_CONTACT_BLOCK,
                extraction_position=ExtractionPosition.CONTACT_BLOCK,
                confidence=self._adjust_confidence(0.56),
                normalization_status=NormalizationStatus.NOT_APPLICABLE,
                normalization_applied=[],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes="Indian location pattern extracted from contact block."
            ))

        return claims

    def _extract_skills(self, skills_text: str, taxonomy: dict, source_name: str, position: ExtractionPosition = ExtractionPosition.NAMED_SECTION) -> list[Claim]:
        """Part 5: Tokenizes skills text and evaluates matches against the taxonomy."""
        claims = []
        
        # Base confidence calculation
        # Named Section: 0.70 * 0.85 * 0.90 = 0.535
        # Prose Body: 0.70 * 0.85 * 0.65 = 0.386
        if position == ExtractionPosition.NAMED_SECTION:
            base_confidence = 0.535
            method = ExtractionMethod.REGEX_SECTION_BODY
        else:
            base_confidence = 0.386
            method = ExtractionMethod.FULL_DOC_SCAN

        # 1. Tokenize skill section string (commas, semicolons, pipes, bullets, newlines)
        tokens = []
        if position == ExtractionPosition.NAMED_SECTION:
            raw_lines = [l.strip() for l in skills_text.split('\n') if l.strip()]
            blocks = []
            current_block = ""
            for line in raw_lines:
                if ":" in line:
                    if current_block:
                        blocks.append(current_block)
                    current_block = line
                else:
                    if current_block:
                        current_block += " " + line
                    else:
                        current_block = line
            if current_block:
                blocks.append(current_block)

            for block in blocks:
                tokens_raw = re.split(r'[,;|•\t\*]+', block)
                for t in tokens_raw:
                    t_clean = t.strip()
                    if not t_clean:
                        continue
                    if ":" in t_clean:
                        t_clean = t_clean.split(":")[-1].strip()
                    if len(t_clean) >= 2 and len(t_clean) <= 50 and not t_clean.isdigit():
                        tokens.append(t_clean)
        else:
            clean_text = skills_text.replace('\n', ' ')
            tokens_raw = re.split(r'[,;|•\t\*]+', clean_text)
            for t in tokens_raw:
                t_clean = t.strip()
                if not t_clean:
                    continue
                if len(t_clean) >= 2 and len(t_clean) <= 50 and not t_clean.isdigit():
                    tokens.append(t_clean)

        for token in tokens:
            token_lower = token.lower()
            matched = False
            match_type = "unverified"
            canonical_name = token  # fallback
            confidence_multiplier = 0.40
            fuzzy_score = None

            # a. Exact match & b. Alias match
            for key, entry in taxonomy.items():
                if token_lower == key:
                    matched = True
                    match_type = "exact"
                    canonical_name = entry["canonical"]
                    confidence_multiplier = 1.00
                    break
                
                aliases_lower = [a.lower() for a in entry.get("aliases", [])]
                if token_lower in aliases_lower:
                    matched = True
                    match_type = "alias"
                    canonical_name = entry["canonical"]
                    confidence_multiplier = 0.95
                    break

            # c. Fuzzy match (only run if exact/alias failed)
            if not matched:
                try:
                    import rapidfuzz
                    for key, entry in taxonomy.items():
                        score = rapidfuzz.fuzz.ratio(token_lower, key)
                        if score > 85:
                            matched = True
                            match_type = "fuzzy"
                            canonical_name = entry["canonical"]
                            confidence_multiplier = 0.75
                            fuzzy_score = float(score)
                            break
                except Exception as e:
                    logger.debug(f"rapidfuzz execution failed: {e}")

            # For PROSE_BODY, skip tokens that do not match the taxonomy exactly or by alias
            if position == ExtractionPosition.PROSE_BODY and match_type not in ["exact", "alias"]:
                continue

            # Calculate final confidence
            final_conf = self._adjust_confidence(base_confidence * confidence_multiplier)

            # Build SkillClaim
            skill_claim = SkillClaim(
                field="skills",
                raw_value=token,
                normalized_value=canonical_name,
                source=source_name,
                source_type=SourceType.UNSTRUCTURED,
                extraction_method=method,
                extraction_position=position,
                confidence=final_conf,
                normalization_status=NormalizationStatus.SUCCESS if match_type in ["exact", "alias", "fuzzy"] else NormalizationStatus.FAILED,
                normalization_applied=["taxonomy_match"],
                corroborated_by=[],
                conflict_with=[],
                extraction_notes=f"Skill matched using {match_type} comparison.",
                canonical_name=canonical_name,
                match_type=match_type,
                fuzzy_score=fuzzy_score
            )
            claims.append(skill_claim)

        return claims

    def _normalize_month(self, m_str: str) -> str:
        """Helper to convert verbal month names to numeric representations ('01'-'12')."""
        return MONTH_MAP.get(m_str.lower().strip(), "01")

    def _date_to_int(self, date_str: str | None, default_present: int = 2026 * 12 + 6) -> int:
        """Converts YYYY-MM or YYYY string formats to an integer representing cumulative months."""
        if not date_str:
            return default_present
        if date_str.lower() in ["present", "current", "now", "ongoing"]:
            return default_present
        
        parts = date_str.split('-')
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            return year * 12 + month
        except Exception:
            return default_present

    def _extract_experience(self, experience_text: str, source_name: str) -> list[ExperienceEntry]:
        """Part 6: Extracts work experience entries, parses date ranges, and checks concurrency."""
        entries = []
        raw_lines = [l.strip() for l in experience_text.split('\n') if l.strip()]
        
        # 1. Identify date lines
        date_lines_info = []
        for idx, line in enumerate(raw_lines):
            start_date = None
            end_date = None
            is_present = False
            company_candidate = None
            matched = False

            # Pattern 1: Month YYYY – Month YYYY
            m1 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\s*[\-–—]\s*({MONTHS_PATTERN})\s+(\d{{4}})\b', line, re.IGNORECASE)
            if m1:
                start_date = f"{m1.group(2)}-{self._normalize_month(m1.group(1))}"
                end_date = f"{m1.group(4)}-{self._normalize_month(m1.group(3))}"
                prefix = line[:m1.start()].strip().rstrip(',|:-').strip()
                if prefix and len(prefix) < 50:
                    company_candidate = prefix
                matched = True

            if not matched:
                # Pattern 2: Month YYYY – Present
                m2 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\s*[\-–—]\s*(present|current|now|ongoing)\b', line, re.IGNORECASE)
                if m2:
                    start_date = f"{m2.group(2)}-{self._normalize_month(m2.group(1))}"
                    end_date = None
                    is_present = True
                    prefix = line[:m2.start()].strip().rstrip(',|:-').strip()
                    if prefix and len(prefix) < 50:
                        company_candidate = prefix
                    matched = True

            if not matched:
                # Pattern 3: YYYY – YYYY
                m3 = re.search(r'\b(\d{4})\s*[\-–—]\s*(\d{4})\b', line)
                if m3:
                    start_date = m3.group(1)
                    end_date = m3.group(2)
                    prefix = line[:m3.start()].strip().rstrip(',|:-').strip()
                    if prefix and len(prefix) < 50:
                        company_candidate = prefix
                    matched = True

            if not matched:
                # Pattern 4: Month YYYY (Start date only)
                m4 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\b', line, re.IGNORECASE)
                if m4:
                    start_date = f"{m4.group(2)}-{self._normalize_month(m4.group(1))}"
                    end_date = None
                    prefix = line[:m4.start()].strip().rstrip(',|:-').strip()
                    if prefix and len(prefix) < 50:
                        company_candidate = prefix
                    matched = True

            if matched:
                date_lines_info.append({
                    "idx": idx,
                    "start_date": start_date,
                    "end_date": end_date,
                    "is_present": is_present,
                    "line": line,
                    "company_candidate": company_candidate
                })

        # Helper to parse a single block of lines
        def parse_experience_block(lines, start_date, end_date, company_candidate, date_line):
            non_date_lines = [l for l in lines if l != date_line]
            title = None
            TITLE_KEYWORDS = {"engineer", "developer", "analyst", "intern", "manager", "lead", "director", "consultant", "architect", "designer", "researcher", "scientist"}
            for line in non_date_lines:
                if any(tk in line.lower() for tk in TITLE_KEYWORDS):
                    title = line
                    break

            company = company_candidate
            COMPANY_INDICATORS = {"inc", "llc", "ltd", "corp", "solutions", "technologies"}
            if not company:
                for line in non_date_lines:
                    if title and line == title:
                        continue
                    if any(ci in line.lower() for ci in COMPANY_INDICATORS):
                        company = line
                        break
            if not company:
                for line in non_date_lines:
                    if title and line == title:
                        continue
                    company = line
                    break

            summary_lines = []
            for line in lines:
                if (title and line == title) or (company and line == company) or (date_line and line == date_line):
                    continue
                summary_lines.append(line)
            
            summary = "\n".join(summary_lines).strip() if summary_lines else None
            adjusted_conf = self._adjust_confidence(0.535)

            if company or title:
                return ExperienceEntry(
                    company=company,
                    title=title,
                    start=start_date,
                    end=end_date,
                    summary=summary,
                    concurrent=False,
                    sources=["resume"],
                    confidence=adjusted_conf
                )
            return None

        # Build entries using date-line grouping
        if date_lines_info:
            claimed_indices = set()
            # 1. Backward scan
            for k, info in enumerate(date_lines_info):
                d_idx = info["idx"]
                claimed_indices.add(d_idx)
                
                backward_lines = []
                prev_d_idx = date_lines_info[k - 1]["idx"] if k > 0 else -1
                for b_idx in range(d_idx - 1, prev_d_idx, -1):
                    line_text = raw_lines[b_idx]
                    if re.match(r'^[^\w\s\(\[\{]', line_text):
                        break
                    match_letter = re.search(r'[a-zA-Z]', line_text)
                    if match_letter and not match_letter.group(0).isupper():
                        break
                    if b_idx in claimed_indices:
                        break
                    backward_lines.insert(0, b_idx)
                    claimed_indices.add(b_idx)
                info["backward_lines"] = backward_lines

            # 2. Forward scan
            for k, info in enumerate(date_lines_info):
                d_idx = info["idx"]
                forward_lines = []
                
                next_limit = len(raw_lines)
                if k + 1 < len(date_lines_info):
                    next_info = date_lines_info[k + 1]
                    if next_info["backward_lines"]:
                        next_limit = next_info["backward_lines"][0]
                    else:
                        next_limit = next_info["idx"]
                        
                for f_idx in range(d_idx + 1, next_limit):
                    forward_lines.append(f_idx)
                    claimed_indices.add(f_idx)
                info["forward_lines"] = forward_lines

            # 3. Process entries
            for info in date_lines_info:
                entry_line_indices = info["backward_lines"] + [info["idx"]] + info["forward_lines"]
                entry_lines = [raw_lines[idx] for idx in entry_line_indices]
                entry = parse_experience_block(
                    entry_lines,
                    info["start_date"],
                    info["end_date"],
                    info["company_candidate"],
                    info["line"]
                )
                if entry:
                    entries.append(entry)
        else:
            # Fallback to double newline split
            blocks = experience_text.split('\n\n')
            for block in blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if not lines:
                    continue
                start_date = None
                end_date = None
                date_line = None
                company_candidate = None
                for line in lines:
                    m1 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\s*[\-–—]\s*({MONTHS_PATTERN})\s+(\d{{4}})\b', line, re.IGNORECASE)
                    if m1:
                        start_date = f"{m1.group(2)}-{self._normalize_month(m1.group(1))}"
                        end_date = f"{m1.group(4)}-{self._normalize_month(m1.group(3))}"
                        date_line = line
                        prefix = line[:m1.start()].strip().rstrip(',|:-').strip()
                        if prefix and len(prefix) < 50: company_candidate = prefix
                        break
                    m2 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\s*[\-–—]\s*(present|current|now|ongoing)\b', line, re.IGNORECASE)
                    if m2:
                        start_date = f"{m2.group(2)}-{self._normalize_month(m2.group(1))}"
                        end_date = None
                        date_line = line
                        prefix = line[:m2.start()].strip().rstrip(',|:-').strip()
                        if prefix and len(prefix) < 50: company_candidate = prefix
                        break
                    m3 = re.search(r'\b(\d{4})\s*[\-–—]\s*(\d{4})\b', line)
                    if m3:
                        start_date = m3.group(1)
                        end_date = m3.group(2)
                        date_line = line
                        prefix = line[:m3.start()].strip().rstrip(',|:-').strip()
                        if prefix and len(prefix) < 50: company_candidate = prefix
                        break
                    m4 = re.search(rf'\b({MONTHS_PATTERN})\s+(\d{{4}})\b', line, re.IGNORECASE)
                    if m4:
                        start_date = f"{m4.group(2)}-{self._normalize_month(m4.group(1))}"
                        end_date = None
                        date_line = line
                        prefix = line[:m4.start()].strip().rstrip(',|:-').strip()
                        if prefix and len(prefix) < 50: company_candidate = prefix
                        break
                entry = parse_experience_block(lines, start_date, end_date, company_candidate, date_line)
                if entry:
                    entries.append(entry)

        # 6. Concurrency Check (Overlapping intervals)
        intervals = []
        for idx, entry in enumerate(entries):
            s_val = self._date_to_int(entry.start)
            e_val = self._date_to_int(entry.end)
            intervals.append((s_val, e_val, idx))

        for i in range(len(intervals)):
            s1, e1, idx1 = intervals[i]
            for j in range(i + 1, len(intervals)):
                s2, e2, idx2 = intervals[j]
                if s1 <= e2 and s2 <= e1:
                    entries[idx1].concurrent = True
                    entries[idx2].concurrent = True

        return entries

    def _extract_education(self, education_text: str) -> list[EducationEntry]:
        """Part 7: Extracts education entries (institutions, degree titles, graduation years)."""
        entries = []
        raw_lines = [l.strip() for l in education_text.split('\n') if l.strip()]

        HEADER_KEYWORDS = {"year", "degree", "certificate", "institute", "cgpa", "board", "passing", "percentage", "mark", "gpa", "institutions", "degrees"}
        
        def is_header_line(text: str) -> bool:
            words = set(re.findall(r'\b\w+\b', text.lower()))
            intersect = words.intersection(HEADER_KEYWORDS)
            if len(intersect) >= 2 and not re.search(r'\b(?:19|20)\d{2}\b', text):
                return True
            return False

        def has_school_indicator(text: str) -> bool:
            return any(re.search(rf'\b{re.escape(ind)}\b', text, re.IGNORECASE) for ind in INSTITUTION_INDICATORS)

        # Identify year lines
        year_lines_info = []
        for idx, line in enumerate(raw_lines):
            matches = re.findall(r'\b(?:19|20)\d{2}\b', line)
            if matches:
                end_year = int(matches[-1])
                year_lines_info.append({
                    "idx": idx,
                    "end_year": end_year,
                    "line": line
                })

        def parse_education_block(lines, default_end_year):
            institution = None
            degree = None
            field = None
            end_year = default_end_year

            if not end_year:
                for line in reversed(lines):
                    match = re.search(r'\b(?:19|20)\d{2}\b', line)
                    if match:
                        end_year = int(match.group(0))
                        break

            # Match Institution Name using indicators first
            ACADEMIC_KEYWORDS = {"business", "systems", "science", "sciences", "engineering", "management", "administration", "arts", "commerce", "design", "law", "studies", "humanities", "social", "applied", "advanced"}
            inst_pattern = r'\b(?:[A-Z][A-Za-z0-9]*\s+){1,3}(?:' + '|'.join(INSTITUTION_INDICATORS) + r')(?:\s+(?:of|and|for))?(?:\s+[A-Z][A-Za-z0-9]*){0,3}\b'
            
            for line in lines:
                inst_match = re.search(inst_pattern, line)
                if inst_match:
                    inst_val = inst_match.group(0)
                    while True:
                        words = inst_val.split()
                        if not words:
                            break
                        first_word = words[0].lower().rstrip(',.:;-')
                        if first_word in ACADEMIC_KEYWORDS:
                            inst_val = " ".join(words[1:])
                        else:
                            break
                    if len(inst_val) > 4:
                        institution = inst_val
                        break

            # Parse Degree and Field
            for line in lines:
                matched_keyword = None
                for keyword in DEGREE_KEYWORDS:
                    if re.search(rf'\b{re.escape(keyword)}\b', line, re.IGNORECASE):
                        matched_keyword = keyword
                        break

                if matched_keyword:
                    start_pos = line.lower().find(matched_keyword.lower())
                    end_pos = len(line)
                    if institution and institution in line:
                        inst_pos = line.find(institution)
                        if inst_pos > start_pos:
                            end_pos = inst_pos
                    
                    degree_text = line[start_pos:end_pos].strip().rstrip(',|:-').strip()
                    degree = degree_text

                    # Extract field
                    field_match = re.search(rf'\b{re.escape(matched_keyword)}\b\s*(?:in|of|\-)?\s*(.*)', degree_text, re.IGNORECASE)
                    if field_match and field_match.group(1):
                        field_val = field_match.group(1).strip()
                        if field_val:
                            field = field_val.strip("()").strip()
                    break

            if not institution:
                for line in lines:
                    has_degree = any(re.search(rf'\b{re.escape(keyword)}\b', line, re.IGNORECASE) for keyword in DEGREE_KEYWORDS)
                    is_year = re.search(r'\b(?:19|20)\d{2}\b', line) and len(line.strip()) < 15
                    if not has_degree and not is_year:
                        institution = line
                        break

            adjusted_conf = self._adjust_confidence(0.535)
            if institution or degree:
                return EducationEntry(
                    institution=institution,
                    degree=degree,
                    field=field,
                    end_year=end_year,
                    sources=["resume"],
                    confidence=adjusted_conf
                )
            return None

        # Build entries using year-line grouping
        if year_lines_info:
            claimed_indices = set()
            # 1. Backward scan
            for k, info in enumerate(year_lines_info):
                d_idx = info["idx"]
                claimed_indices.add(d_idx)
                
                backward_lines = []
                prev_d_idx = year_lines_info[k - 1]["idx"] if k > 0 else -1
                for b_idx in range(d_idx - 1, prev_d_idx, -1):
                    line_text = raw_lines[b_idx]
                    if is_header_line(line_text):
                        break
                    if b_idx in claimed_indices:
                        break
                    if has_school_indicator(raw_lines[d_idx]):
                        break
                    if has_school_indicator(line_text):
                        # Include this institution line, but stop scanning backward beyond it
                        backward_lines.insert(0, b_idx)
                        claimed_indices.add(b_idx)
                        break
                    backward_lines.insert(0, b_idx)
                    claimed_indices.add(b_idx)
                info["backward_lines"] = backward_lines

            # 2. Forward scan
            for k, info in enumerate(year_lines_info):
                d_idx = info["idx"]
                forward_lines = []
                
                next_limit = len(raw_lines)
                if k + 1 < len(year_lines_info):
                    next_info = year_lines_info[k + 1]
                    if next_info["backward_lines"]:
                        next_limit = next_info["backward_lines"][0]
                    else:
                        next_limit = next_info["idx"]
                        
                for f_idx in range(d_idx + 1, next_limit):
                    forward_lines.append(f_idx)
                    claimed_indices.add(f_idx)
                info["forward_lines"] = forward_lines

            # 3. Process entries
            for info in year_lines_info:
                entry_line_indices = info["backward_lines"] + [info["idx"]] + info["forward_lines"]
                entry_lines = [raw_lines[idx] for idx in entry_line_indices]
                entry = parse_education_block(entry_lines, info["end_year"])
                if entry:
                    entries.append(entry)
        else:
            # Fallback to double newline split
            blocks = education_text.split('\n\n')
            for block in blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if not lines:
                    continue
                entry = parse_education_block(lines, None)
                if entry:
                    entries.append(entry)

        return entries

    def _scan_prose_for_skills(self, prose_text: str, taxonomy: dict, source_name: str) -> list[SkillClaim]:
        """Scans prose blocks for exact and alias taxonomy matches to emit SkillClaims."""
        if not prose_text:
            return []

        claims = []
        # Base prose confidence: 0.70 (source) * 0.85 (method) * 0.65 (position) = 0.386
        base_confidence = 0.386

        # Tokenize prose into separate words/phrases
        tokens_raw = re.split(r'[,;|•\n\-\*]+', prose_text)
        tokens = []
        for t in tokens_raw:
            t_clean = t.strip()
            if len(t_clean) >= 2 and len(t_clean) <= 50 and not t_clean.isdigit():
                tokens.append(t_clean)

        for token in tokens:
            token_lower = token.lower()
            matched = False
            match_type = None
            canonical_name = None
            confidence_multiplier = 0.0

            # Scan taxonomy for exact/alias hits only
            for key, entry in taxonomy.items():
                if token_lower == key:
                    matched = True
                    match_type = "exact"
                    canonical_name = entry["canonical"]
                    confidence_multiplier = 1.00
                    break
                
                aliases_lower = [a.lower() for a in entry.get("aliases", [])]
                if token_lower in aliases_lower:
                    matched = True
                    match_type = "alias"
                    canonical_name = entry["canonical"]
                    confidence_multiplier = 0.95
                    break

            if matched:
                final_conf = self._adjust_confidence(base_confidence * confidence_multiplier)
                skill_claim = SkillClaim(
                    field="skills",
                    raw_value=token,
                    normalized_value=canonical_name,
                    source=source_name,
                    source_type=SourceType.UNSTRUCTURED,
                    extraction_method=ExtractionMethod.FULL_DOC_SCAN,
                    extraction_position=ExtractionPosition.PROSE_BODY,
                    confidence=final_conf,
                    normalization_status=NormalizationStatus.SUCCESS,
                    normalization_applied=["taxonomy_match"],
                    corroborated_by=[],
                    conflict_with=[],
                    extraction_notes=f"Prose skill matched using {match_type} comparison.",
                    canonical_name=canonical_name,
                    match_type=match_type,
                    fuzzy_score=None
                )
                claims.append(skill_claim)

        return claims

    def extract(self, file_path: str, detected_type: str, taxonomy: dict) -> list[Claim]:
        """Part 8: Main extract entry point routing sections and collecting claims."""
        self.warnings = []
        self.near_empty = False
        self.no_sections_detected = False

        source_name = os.path.basename(file_path)

        # 1. Text Extraction
        extract_res = self._extract_text(file_path, detected_type)
        raw_text = extract_res.get("text", "")
        
        # Handle warnings propagated from extraction routines
        if "warning" in extract_res:
            self.warnings.append(extract_res["warning"])

        char_count = len(raw_text)
        if char_count < 50:
            self.near_empty = True
            self.warnings.append(f"Extracted text is near empty ({char_count} chars). Confidence scores penalized.")

        # 2. Text Cleaning
        cleaned_text = self._clean_text(raw_text)

        # 3. Section Detection
        sections = self._detect_sections(cleaned_text)

        claims: list[Claim] = []

        # 4. Extract Contact details (always present in first 15 lines)
        contact_text = sections.get("CONTACT_BLOCK", "")
        if contact_text:
            claims.extend(self._extract_contact(contact_text, source_name))

        # 5. Extract Skills
        skills_text = sections.get("SKILLS", sections.get("TECHNICAL_SKILLS", None))
        if skills_text:
            # Parse from dedicated named section
            claims.extend(self._extract_skills(skills_text, taxonomy, source_name, ExtractionPosition.NAMED_SECTION))
        else:
            # Fall back to scan full document for skills if no named skills section exists
            claims.extend(self._extract_skills(cleaned_text, taxonomy, source_name, ExtractionPosition.FULL_DOCUMENT))

        # Scan EXPERIENCE and PROJECTS sections for prose body skills
        exp_prose = sections.get("EXPERIENCE", "")
        proj_prose = sections.get("PROJECTS", "")
        if exp_prose:
            claims.extend(self._scan_prose_for_skills(exp_prose, taxonomy, source_name))
        if proj_prose:
            claims.extend(self._scan_prose_for_skills(proj_prose, taxonomy, source_name))

        # 6. Extract Experience
        if exp_prose:
            exp_entries = self._extract_experience(exp_prose, source_name)
            if exp_entries:
                # Wrap ExperienceEntry list inside a composite Claim object
                # Base confidence: 0.70 * 0.85 * 0.90 = 0.535
                adjusted_conf = self._adjust_confidence(0.535)
                # Check concurrency notes
                has_concurrent = any(e.concurrent for e in exp_entries)
                note = "Experience section parsed into entries. Concurrent roles detected." if has_concurrent else "Experience section parsed into entries."
                
                claims.append(Claim(
                    field="experience",
                    raw_value=exp_entries,
                    normalized_value=None,
                    source=source_name,
                    source_type=SourceType.UNSTRUCTURED,
                    extraction_method=ExtractionMethod.REGEX_SECTION_BODY,
                    extraction_position=ExtractionPosition.NAMED_SECTION,
                    confidence=adjusted_conf,
                    normalization_status=NormalizationStatus.NOT_APPLICABLE,
                    normalization_applied=[],
                    corroborated_by=[],
                    conflict_with=[],
                    extraction_notes=note
                ))

        # 7. Extract Education
        edu_text = sections.get("EDUCATION", "")
        if edu_text:
            edu_entries = self._extract_education(edu_text)
            if edu_entries:
                # Wrap EducationEntry list inside a composite Claim object
                adjusted_conf = self._adjust_confidence(0.535)
                claims.append(Claim(
                    field="education",
                    raw_value=edu_entries,
                    normalized_value=None,
                    source=source_name,
                    source_type=SourceType.UNSTRUCTURED,
                    extraction_method=ExtractionMethod.REGEX_SECTION_BODY,
                    extraction_position=ExtractionPosition.NAMED_SECTION,
                    confidence=adjusted_conf,
                    normalization_status=NormalizationStatus.NOT_APPLICABLE,
                    normalization_applied=[],
                    corroborated_by=[],
                    conflict_with=[],
                    extraction_notes="Education section parsed into entries."
                ))

        return claims
