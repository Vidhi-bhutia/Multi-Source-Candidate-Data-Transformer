# Candidate Transformer - Edge Cases & Architectural Limitations

This document lists the candidate ingestion edge cases handled by the transformer engine, alongside a list of intentionally descoped items.

---

## 1. Handled Ingestion Edge Cases

### A. Scanned Resumes (OCR Fallback)
- **Problem**: Resumes that are scanned images wrapped in a PDF envelope contain zero text stream characters, causing standard text parsers to return empty files.
- **Solution**: The `SourceDetector` monitors character counts. If a PDF contains fewer than 100 characters in its first three pages, it flags the file as `image_pdf`. The `ResumeExtractor` then initiates a fallback using `pytesseract` to perform layout-aware Optical Character Recognition (OCR) on rendered page images.

### B. Overlapping Contract Timelines (Experience Years)
- **Problem**: Resumes frequently contain overlapping timelines (e.g. concurrent freelance work, parallel jobs). Summing raw job durations would inflate the candidate's actual years of experience.
- **Solution**: The `EvidenceArbitrationEngine` converts dates into numeric month values. It builds timeline segments and merges overlapping intervals using interval range union mathematics. The total years of experience is computed solely on the net non-overlapping work periods.

### C. Present/Ongoing Career Durations
- **Problem**: End dates on resumes are often written as verbal keywords like "Present", "Current", "Now", or "Ongoing".
- **Solution**: The normalizer standardizes these terms to the execution date by querying the pipeline's runtime timestamp (e.g., `2026-06-21`), ensuring precise experience month counts.

### D. Inline Date and Company Text
- **Problem**: Resume builders often format roles with the company name and date range on the same line (e.g. `People Prudent Feb 2026 - Present`). Traditional paragraph splitters might skip this line or misidentify the company name as a bullet point.
- **Solution**: The experience parser uses regex matches for dates. If a date matches, it captures the text preceding the match on that line (trimming symbols like `|` or `,`) and resolves it as the company name.

### E. Phone Number Format Variations
- **Problem**: Candidates record phone numbers in numerous local formats: with/without country codes, brackets, spaces, or hyphens (e.g. `+91 96858-56291`, `(968) 585-6291`, `9685856291`).
- **Solution**: The phone normalizer utilizes the Google `phonenumbers` library to parse and sanitize values to strict E.164 formats, validating against regional phone format rules.

### F. Skills Taxonomy Mappings
- **Problem**: Skills are listed with abbreviations, aliases, or spelling variations (e.g. "py", "JS", "Microsoft Excel").
- **Solution**: The parser tokenizes sections using commas and bullets, matching terms against a structured taxonomy ontology. It maps abbreviations to their canonical name (e.g. "py" ➔ "Python") using exact, alias, and fuzzy matching (via `rapidfuzz` ratio > 85).

### G. Empty & Corrupt Input Files
- **Problem**: Missing, empty, or unreadable files can cause crashes.
- **Solution**: The `SourceDetector` performs pre-flight checks (existence check, size check, header inspections). Any failing check appends warnings to pipeline metadata, returning an empty profile rather than crashing the execution.

### H. Education Entry Misalignment (Missing Double Newlines)
- **Problem**: When a resume lists multiple education histories without double-newline spacing (e.g., adjacent lines), the parser's backward scanning logic might incorrectly group the degree and field details of one school into the subsequent entry (e.g. attaching university degree details to a high school entry).
- **Solution**: The education parser checks if a year line contains an institution indicator (like `Institute`, `Vidyalaya`, `School`). If it does, the parser halts the backward scan immediately, ensuring that degree description lines are kept aligned with their correct parent institution.

---

## 2. Intentionally Descoped (Architectural Limitations)

The following capabilities were deliberately excluded to maintain deterministic behavior, keep the system lightweight, and prevent third-party token requirements:

1. **Named Entity Recognition (NER) ML Models**: Deep Learning models were descoped. Instead, the engine uses section-aware regular expressions and structured taxonomy lookups to guarantee 100% predictable execution paths, eliminate hallucinated fields, and maintain processing speeds.
2. **Direct Image File Uploads (PNG/JPG)**: Ingestion is restricted to PDF, DOCX, and CSV formats. Raw image files must be converted into PDF documents before uploading to allow OCR page rendering.
3. **Live Profile Fetching (LinkedIn/GitHub API)**: Profile data is parsed from text directly. Live queries are omitted to prevent API rate-limiting issues and to avoid requiring user access tokens.
4. **Batch Orchestration**: The core pipeline processes one profile at a time (one CSV candidate and one resume). Multi-candidate batch loops must be implemented in wrapping scripts.
