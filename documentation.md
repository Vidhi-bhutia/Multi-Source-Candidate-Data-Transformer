# Candidate Transformer - Comprehensive Technical Reference

This document provides a highly detailed architectural, functional, and operational breakdown of the Multi-Source Candidate Data Transformer engine.

---

## 1. Pipeline Architecture Flow (End-to-End)

The transformer consumes data from multiple messy sources and processes them through an 11-stage, type-safe, claim-based pipeline:

```
[Inputs] ➔ Input Validator ➔ Source Detector ➔ CSV/Resume Extractors ➔ Raw Claim Builder ➔ Normalization Engine ➔ Arbitration Engine ➔ Canonical Builder ➔ Custom Config Projector ➔ Schema Validator ➔ [API/UI JSON]
```

1. **Input Validation (`pipeline.py`)**: Asserts that execution arguments are present and verifies that at least one candidate document path (`csv_path` or `resume_path`) is supplied.
2. **Source Detection (`source_detector.py`)**: Reads the file header bytes using MIME classification. Scanned documents are checked by calculating the character-to-page density (less than 100 characters in the first 3 pages flags a scanned PDF).
3. **Claims Extraction (`csv_extractor.py`, `resume_extractor.py`)**: Parses raw files. Structured files map directly. Unstructured resumes segment layout boundaries (CONTACT, EXPERIENCE, EDUCATION, SKILLS) before executing targeted search rules.
4. **Claim Compilation (`models.py`)**: Encapsulates raw values into immutable `Claim` models. These log the source filename, extraction method, position in the document, and a raw confidence weight.
5. **Normalization Engine (`normalizer.py`)**: Sanitizes and standardizes text into canonical formats (E.164 phone formats, YYYY-MM dates, ISO country mapping, and skills taxonomy alignments).
6. **Cross-Source Alignment (`arbitration.py`)**: Collects all normalized claims and groups them by their primary email hash.
7. **Cross-Source Arbitration (`arbitration.py`)**: Performs field merging:
   - **Union Strategy**: Merges arrays (emails, phones, skills, experience, education). Identical entries receive a **+0.15 corroboration bonus**.
   - **Highest Confidence Strategy**: Merges single-value fields (name, location, headline).
   - **Conflict Detection**: Compares winning claims against competitors; if the confidence margin is <= 0.05, a conflict flag is raised in provenance.
8. **Years of Experience Union (`arbitration.py`)**: Resolves parallel jobs and overlapping contracts by projecting timelines onto a unified array of work months, counting only the net sum of non-overlapping months.
9. **Canonical Profile Builder (`canonical_builder.py`)**: Creates a secure, immutable `CanonicalCandidate` object with a unique SHA-256 ID.
10. **Output Projector (`projector.py`)**: Customizes outputs at runtime by evaluating dot-notation paths (e.g. `emails[0]`, `experience[0].company`) onto client-specified fields.
11. **Pydantic Schema Validation (`validator.py`)**: Runs projected schemas through structural models to verify required fields and types, generating diagnostic warning and error collections.

---

## 2. Exhaustive Module Breakdown

### `app/pipeline/models.py`
Defines the Pydantic data schemas representing the engine's data structures:
- `Claim`: Stores the raw extracted value, target field, extraction method (enum), document position (enum), source type (structured vs unstructured), source filename, confidence score, and normalization status.
- `SkillClaim` (inherits `Claim`): Adds skills metadata (match type, canonical name, fuzzy score).
- `ExperienceEntry`: Repesents parsed career roles (company, title, start, end, summary, concurrency flag, sources list, confidence).
- `EducationEntry`: Represents parsed academic history (institution, degree, field, graduation end year, sources list, confidence).
- `CanonicalCandidate`: Represents the finalized profile. Contains fields, provenance records, processed source names, overall confidence, run timestamp, and warnings.
- `ProjectionConfig`: Defines field cast specifications for dynamic reshaping.

### `app/pipeline/source_detector.py`
- **Logic**: Inspects file headers to classify raw documents into `csv`, `pdf`, `image_pdf`, `docx`, or `unknown`.
- **Scanned PDF Check**: Iterates through the first 3 pages using `pdfplumber`. If the total extracted characters are less than 100, the PDF is flagged as scanned (`image_pdf`), bypassing normal text stream extractors.
- **Header Verification**: Inspects columns for CSV files to log alerts if no recognizable candidate fields are found.

### `app/pipeline/extractors/csv_extractor.py`
- **Logic**: Processes recruiter spreadsheets. Maps headers to canonical fields using fuzzy column name heuristics (e.g. "Full Name", "Candidate Name", "name" map to `full_name`).
- **Confidence**: Assigns a high baseline score of 0.95, representing data from verified, structured databases.

### `app/pipeline/extractors/resume_extractor.py`
- **Logic**: Splits unstructured resumes page-by-page.
- **Section Segmentation**: Scans for standard headers (e.g. "Work Experience", "Education", "Technical Skills") using regex matches to partition the document into section strings (limiting searching scopes).
- **Inline Date/Company Parsing**: Matches date ranges in experience blocks. If a date pattern (e.g. `Feb 2026 - Present`) matches, it extracts the line prefix preceding the match and registers it as the company name.
- **Skills Taxonomy Match**: Tokenizes text using delimiters (commas, pipes, bullets) and maps them against a taxonomy ontology using exact checks, alias matching, and fuzzy string ratios (via `rapidfuzz` > 85).

### `app/pipeline/normalizer.py`
- **Phone Formatting**: Uses the Google `phonenumbers` library, verifying formatting using regional presets (defaulting to IN, falling back to US, then global).
- **Date Normalization**: Matches verbal month abbreviations (e.g. "Jun", "Sept") and maps them to numeric formats (`06`, `09`) alongside a 4-digit year.
- **Country Codes**: Matches city text against major lists to normalize country keys to standard ISO-3166 alpha-2 formats.

### `app/pipeline/arbitration.py`
- **Union Strategy**: Dedupes lists, boosting identical entries by +0.15 confidence.
- **Highest Confidence Strategy**: Compares all single-value claims and picks the one with the highest confidence. Logs conflict markers if competing values have close confidence scores (margin <= 0.05).
- **Timeline Intersection Calculator**: 
  - Converts start and end dates to a numeric month value.
  - Combines overlapping intervals using range union math.
  - Computes final years of experience: `total_months / 12` rounded to 1 decimal place.

### `app/pipeline/projector.py`
- **Logic**: Reshapes canonical candidate profiles using paths at runtime.
- **Dot-Notation Selectors**: Recursively resolves indexes like `emails[0]` or nested fields like `experience[0].company` by splitting selectors.
- **On Missing Behaviors**: Appends nulls, deletes fields (`omit`), or triggers structural errors (`error`) based on the active config configuration.

### `app/pipeline/validator.py`
- **Logic**: Validates projected records against structural layouts using dynamic Pydantic models. Returns error details if checks fail.
