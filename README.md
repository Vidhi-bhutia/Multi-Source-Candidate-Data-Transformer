# Multi-Source Candidate Data Transformer

The Multi-Source Candidate Data Transformer is a robust, production-grade profile ingestion and standardization pipeline. It is designed to consume candidate data from both structured recruiter spreadsheets (CSV) and unstructured resumes (PDF, DOCX, scanned image PDFs via OCR), resolve duplicate or conflicting records using an evidence-based arbitration engine, and project the canonical profile onto a runtime-configurable schema. The system validates the output against customizable data expectations, ensuring data integrity for downstream search and applicant tracking systems.

## Design Philosophy

The transformer utilizes a **claim-based evidence architecture** where every extracted datum is stored as an independent `Claim` containing metadata about its source, extraction method, and initial confidence. Instead of destructively merging or overwriting profile fields, the pipeline aggregates all claims and applies mathematical confidence rules to arbitrate conflicts. The design prioritizes data truthfulness, operating under the principle that **wrong-but-confident data is far worse than honestly-empty fields**; when validation or normalizations fail, the system falls back to empty values with transparent warnings rather than guessing or asserting corrupt formats.

## Architecture

```
Source Files ➔ Source Detector ➔ [CSV Extractor | Resume Extractor] ➔ Claim Builder ➔ Normalization Engine ➔ Evidence Arbitration Engine ➔ Canonical Candidate Builder ➔ Projection Engine ➔ Schema Validator ➔ Final JSON Output
```

- **Source Detector**: Dynamically inspects incoming file headers using `python-magic` and `pdfplumber` to verify file integrity, detect scanned layouts, and route to the correct extractor.
- **CSV Extractor**: Standardizes and parses structured columns (e.g., emails, phone numbers, headlines) using configurable column header mapping rules.
- **Resume Extractor**: Segments unstructured document text into localized sections (like CONTACT, EXPERIENCE, and SKILLS) to limit extraction scopes and run targeted regular expressions.
- **Claim Builder**: Encapsulates raw values into standard `Claim` models that document confidence levels, extraction positions, and provenance details.
- **Normalization Engine**: Validates, sanitizes, and standardizes claims (e.g., formatting phones to E.164, dates to ISO YYYY-MM, names to title-case) without modifying raw values.
- **Evidence Arbitration Engine**: Resolves competing claims across sources by identifying corroboration (confidence boosting) and handling tiebreaks based on source priority and confidence margins.
- **Canonical Candidate Builder**: Combines arbitrated values and provenance records to compile a secure `CanonicalCandidate` object with a unique SHA-256 ID.
- **Projection Engine**: Dynamically reshapes and casts the immutable canonical candidate dictionary into a configured output schema at runtime using dot-notation selectors.
- **Schema Validator**: Validates the projected output against Pydantic-based rules, returning structured compliance logs with warnings and error lists.

## Sources Supported

- **Recruiter CSV (structured)**: Automated row parsing with validation on required headers.
- **Resume PDF — text-based (unstructured)**: Direct textual stream parsing page-by-page.
- **Resume PDF — scanned/image-based with OCR fallback (unstructured)**: Automated image extraction and layout analysis, utilizing Tesseract OCR fallback for scanned PDF documents.
- **Resume DOCX (unstructured)**: Native Word file parsing and block text extraction.

## Requirements

- **Python 3.10+**
- **tesseract-ocr** system package (required for OCR on scanned PDFs)
  - **macOS**: `brew install tesseract`
  - **Ubuntu**: `sudo apt install tesseract-ocr`
  - **Windows**: Install the binary installer and add Tesseract to your PATH.

## Setup

```bash
git clone https://github.com/Vidhi-bhutia/Multi-Source-Candidate-Data-Transformer.git
pip install -r requirements.txt
python run.py
```

## Running the Pipeline

### Web UI
1. Run the local Flask server:
   ```bash
   python run.py
   ```
2. Navigate to [http://localhost:5000](http://localhost:5000) in your browser.
3. Drag-and-drop a CSV and/or Resume file, paste or upload a custom JSON schema config, and run the pipeline. Inspect parsed claims, provenance timelines, and schema validation statuses interactively.

### CLI
Run the pipeline directly from your terminal using the built-in module entry point:
```bash
python -m app.pipeline.pipeline --csv sample_data/candidates.csv --resume ../sample_data/vidhi_resume.pdf --config sample_data/configs/custom_config.json
```

## Running Tests
Execute the comprehensive unit and integration test suite via pytest:
```bash
pytest tests/ -v
```

## Sample Output

Running the pipeline on `candidates.csv` and `vidhi_resume.pdf` with the `custom_config.json` yields the following projected JSON structure:

```json
{
  "success": true,
  "canonical": {
    "candidate_id": "84108d3a34daa1f2b8e53b04d05f93fed96c441f4e3dfbc82c208b6a5018ded2",
    "full_name": "Vidhi Bhutia",
    "emails": [
      "vidhibhutia2407@gmail.com"
    ],
    "phones": [
      "+919685856291"
    ],
    "years_experience": 0.4,
    "skills": [
      {"name": "Python", "confidence": 0.95, "sources": ["candidates.csv", "vidhi_resume.pdf"]}
    ]
  },
  "projected": {
    "full_name": "Vidhi Bhutia",
    "primary_email": "vidhibhutia2407@gmail.com",
    "phone": "+919685856291",
    "skills": [
      "Python",
      "JavaScript",
      "Flask",
      "Next.Js"
    ],
    "years_experience": 0.4,
    "current_company": "IT & Software Intern",
    "linkedin": "linkedin.com/in/vidhi-bhutia"
  },
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": []
  },
  "pipeline_meta": {
    "sources_processed": [
      "candidates.csv",
      "vidhi_resume.pdf"
    ],
    "all_warnings": [
      "Phone normalization failed for value '2022 - 2026'"
    ],
    "pipeline_run_timestamp": "2026-06-20T12:06:14.056195Z"
  }
}
```

## Configurable Output

The projector reshaping system uses a schema-based mapping strategy configured via JSON files. This allows runtime modifications to the output structure without editing code:

- **`sample_data/configs/default_config.json`**: An empty fields configuration. This instructs the pipeline to bypass custom projection and return the raw, un-flattened `CanonicalCandidate` object including full details.
- **`sample_data/configs/custom_config.json`**: Restructures the candidate into a specific API format. It flattens lists (e.g. `emails[0]` ➔ `primary_email`), extracts nested fields (e.g. `experience[0].company` ➔ `current_company`), normalizes lists of skills, and strips out nested provenance arrays by setting `include_provenance` to `false`.

## Edge Cases Handled

- **Empty Files**: Gracefully flags empty files without throwing unhandled exceptions or crashing the pipeline.
- **Unmapped CSV Columns**: Logs a warning and continues with zero claims if no expected headers match the column map.
- **Unstructured / Missing Resume Sections**: Applies a confidence penalty to claims when no clear headers exist, analyzing the entire document as prose.
- **Ambiguous Dates / "Present"**: Standardizes timeline terms like "Present" or "Current" to the current date dynamically using the runtime execution timestamp.
- **Phone Number Parsing**: Resolves regional numbers (defaulting to IN, fallback to US, then global) using robust parsing libraries.
- **Deduplicating Multi-Emails**: Automatically extracts only the first valid email address from comma- or semicolon-separated fields.
- **Taxonomy Normalization**: Maps variations and aliases (e.g. "py" ➔ "Python", "js" ➔ "JavaScript") using a predefined skills taxonomy.
- **Concurrent Experience Deduplication**: Implements timeline interval union math to prevent double-counting overlapping work dates when computing experience years.

## Deliberately Descoped

- **Batch multi-candidate processing**: Descoped to focus on core extraction and arbitration quality (can be easily wrapped in a simple loop wrapper).
- **LinkedIn/GitHub live API fetch**: Kept to parsing URLs from text rather than live API calls to prevent rate-limiting and access token requirements.
- **ML-based Named Entity Recognition (NER)**: Replaced with section-aware regex matching and deterministic taxonomy lookups to guarantee 100% predictable output behaviors.
- **OCR for raw image files**: File formats like JPEG/PNG must be converted to PDF first; the pipeline limits native OCR to scanned PDF documents.

## Design Decisions

### 1. Why Claim-Based Architecture Over Direct Field Merging
Ingesting data from multiple sources requires keeping track of where every piece of information originated. By treating each data point as a separate, trackable `Claim`, the pipeline preserves provenance, confidence weightings, and normalization histories. This makes the system self-documenting and auditable, allowing downstream applications to trace exactly why a phone number or email was preferred, or how a confidence score was computed.

### 2. Why Section-Aware Parsing Over Full-Document Regex
Using global regular expressions on full resume texts is highly error-prone. For instance, a university or previous employer name could easily be misidentified as the candidate's current employer. Segmenting documents into logical boundaries (such as EXPERIENCE, EDUCATION, or CONTACT) before running targeted regex patterns isolates the extraction scope, significantly reducing false-positive rates and maintaining high precision.

### 3. Why Computed Years of Experience Over Stated Values
Resumes frequently contain exaggerations or inconsistencies in stated work durations. Calculating years of experience programmatically by standardizing extracted job blocks, projecting them onto a unified timeline, and performing interval union arithmetic (deduplicating concurrent overlapping roles) guarantees an objective, mathematical metric that accurately reflects true career duration.
