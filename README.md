# Multi-Source Candidate Data Transformer: A Trust-Aware Evidence Fusion Pipeline

This repository contains the **Multi-Source Candidate Data Transformer**, a Python-based pipeline that ingests heterogeneous candidate profile data from structured (CSV) and unstructured sources (PDF, scanned PDF, DOCX), resolves candidate identities, arbitrates conflicting evidence, and projects profiles into configurable schemas.

---

## 1. Quick Start (How to Run)

### Setup & Installation
Requires **Python 3.10+** (includes CPU-based `easyocr` for scanned image PDFs).

```bash
# Clone the repository
git clone https://github.com/Vidhi-bhutia/Multi-Source-Candidate-Data-Transformer.git
cd Multi-Source-Candidate-Data-Transformer

# Create & activate a virtual environment
python -m venv venv
# On macOS/Linux:
source venv/bin/activate
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### Run the Web UI Dashboard
To run the interactive web interface:
```bash
python run.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser. Drag and drop resumes/CSVs, configure projection mappings, and trigger the transformation pipeline in real time.

### Run the CLI Tool
To process candidate sources from the terminal:
```bash
python -m app.pipeline.pipeline --csv sample_data/candidates.csv --resume sample_data/vidhi_resume.pdf --config sample_data/configs/custom_config.json
```

### Running Tests
To execute all 23 backend unit and integration tests:
```bash
python -m pytest tests/ -v
```

---

## 2. Key Engineering Assumptions

1. **Identity Resolution**: Email matches serve as the primary unique candidate identifier across multiple source documents.
2. **Timeline & Experience Math**: Overlapping employment intervals (such as concurrent or freelance roles) are merged using range union arithmetic before calculating total years.
3. **Date Normalization**: Verbal timelines (e.g. "Present", "Current") normalize to the pipeline run month/year.
4. **Fuzzy Skill Alignments**: Raw skill tokens match against a 370+ keyword taxonomy ontology using Exact, Alias, and Fuzzy matching (via RapidFuzz ratio > 85).
5. **OCR Fallback**: Scanned PDFs are detected by page-character density (less than 100 characters in the first 3 pages) and fall back to local CPU-only `easyocr` rendering.
6. **Confidence Scoring**: Computed per-field based on source base trust (structured=1.0, unstructured=0.7) and extraction method weight, plus a `+0.15` corroboration bonus for identical cross-source claims.

---

## 3. Deliberately Descoped Items

1. **Named Entity Recognition (NER) Deep Learning Models**: Avoided for deterministic regex/taxonomy logic to ensure execution speed and zero hallucinations.
2. **Direct Image Formats (PNG/JPG)**: Ingestion is restricted to CSV, PDF, and DOCX.
3. **Live Profile Scraping**: Social platform profiles must be provided as local files rather than fetched over live APIs to prevent rate limits.
4. **Distributed Queue/Batch Processing**: Single-execution pipeline; scale is handled via parallel processes.

---

## 4. Architectural & System Guides

For a comprehensive deep dive into the system-level details, schemas, mathematical formulas, and function guides, please refer to:
- [documentation.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Projects/Eightfold%20Assignment/documentation.md) (Architecture, Module Breakdown, Formulas, and Taxonomy)
- [edge_cases.md](file:///c:/Users/LENOVO/OneDrive/Desktop/Projects/Eightfold%20Assignment/edge_cases.md) (Edge cases and error-handling specs)
