import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_pdf():
    pdf_path = "VidhiBhutia_vidhibhutia2407@gmail.com_Eightfold.pdf"
    
    # 612 x 792 points. With 20pt margins, printable area is 572 x 752 points.
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=20,
        rightMargin=20,
        topMargin=20,
        bottomMargin=20
    )
    
    styles = getSampleStyleSheet()
    
    # Define color scheme
    primary_color = colors.HexColor('#4a121a')  # deep wine
    secondary_color = colors.HexColor('#1e293b') # slate
    light_bg = colors.HexColor('#f8fafc')       # light slate
    border_color = colors.HexColor('#cbd5e1')
    accent_color = colors.HexColor('#64748b')
    
    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=primary_color
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=accent_color
    )
    
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=secondary_color,
        alignment=2 # Right aligned
    )
    
    h1_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=primary_color,
        spaceAfter=3
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        leading=8.5,
        textColor=secondary_color
    )
    
    bullet_style = ParagraphStyle(
        'BulletTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        leading=8,
        textColor=secondary_color,
        leftIndent=8
    )
    
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.5,
        leading=8,
        textColor=colors.white
    )
    
    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6,
        leading=7.5,
        textColor=secondary_color
    )
    
    story = []
    
    # ------------------ TITLE BLOCK ------------------
    title_text = "TECHNICAL DESIGN: MULTI-SOURCE CANDIDATE DATA TRANSFORMER"
    subtitle_text = "Stage 1 Architectural Blueprint • Deterministic & Configurable Profile Ingestion Engine"
    meta_text = "Candidate: Vidhi Bhutia<br/>Email: vidhibhutia2407@gmail.com"
    
    header_data = [
        [
            Paragraph(f"<b>{title_text}</b><br/>{subtitle_text}", title_style),
            Paragraph(meta_text, meta_style)
        ]
    ]
    
    header_table = Table(header_data, colWidths=[382, 190])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6))
    
    # Decorative line
    line_table = Table([[""]], colWidths=[572], rowHeights=[1.5])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), primary_color),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 8))
    
    # ------------------ SECTION 1: INGESTION PIPELINE BREAKDOWN ------------------
    story.append(Paragraph("1. PIPELINE WORKFLOW & DATA PIPES", h1_style))
    pipeline_intro = (
        "The engine operates as a sequential transformation pipeline where candidate data flows through 9 distinct stages. "
        "Every raw datum is encapsulated into an independent <b>Claim</b> object keeping track of its source, extraction method, position, and confidence. "
        "This claim-based model preserves auditability and prevents data loss prior to arbitration."
    )
    story.append(Paragraph(pipeline_intro, body_style))
    story.append(Spacer(1, 4))
    
    pipeline_stages = [
        ["Step / Layer", "Inputs & Formats", "Functional Operation & Core Logic", "Outputs Generated"],
        ["1. Input Validation", "CSV files, PDF/DOCX resumes", "Validates file formats, sizes, and verifies that at least one file is provided.", "File descriptors, error alerts"],
        ["2. Source Detection", "Raw source file byte streams", "Uses python-magic to verify MIME headers, detects scanned PDFs by character density.", "File meta, image/scanned flags"],
        ["3. Claims Extraction", "Structured CSV & Unstructured PDF/DOCX", "Extracts structured rows via Column Map; segments PDFs into sections (CONTACT, EXPERIENCE, SKILLS) before targeted regex matches.", "Raw Claim objects array"],
        ["4. Ingestion Normalizer", "Raw un-standardized Claims", "Validates and normalizes data values (E.164 phone parsing, YYYY-MM dates, ISO-2 country mappings, skills lookups).", "Standardized Claim objects"],
        ["5. Cross-Source Arbitration", "Standardized Claims collection", "Aligns duplicate profiles by primary email. Executes Union (lists) and Highest Confidence (single-value) strategies.", "Canonical field values & Provenance"],
        ["6. Canonical Builder", "Arbitrated data properties", "Aggregates winning values and computes unique SHA-256 candidate ID based on normalized email string.", "CanonicalCandidate schema model"],
        ["7. Output Projector", "CanonicalCandidate, ProjectionConfig", "Reshapes the output based on runtime configuration (dot-notation mapping, field inclusion/exclusion, provenance toggle).", "Projected payload dictionary"],
        ["8. Schema Validator", "Projected payload, schema expectations", "Validates structural fields, required keys, and types using Pydantic models. Degrades gracefully on missing items.", "Diagnostic log (warnings/errors)"],
        ["9. API/UI Delivery", "Projected output + diagnostic logs", "Serializes and delivers final validated payload to the Flask Web dashboard, CLI terminal, or API responses.", "Final standardized JSON output"]
    ]
    
    p_table = Table(pipeline_stages, colWidths=[92, 105, 275, 100])
    p_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,0), 3),
        ('TOPPADDING', (0,0), (-1,0), 3),
        ('BOTTOMPADDING', (0,1), (-1,-1), 2.5),
        ('TOPPADDING', (0,1), (-1,-1), 2.5),
        ('BACKGROUND', (0,1), (-1,-1), light_bg),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
    ]))
    
    # Wrap text in paragraphs for cells
    for r in range(len(pipeline_stages)):
        for c in range(len(pipeline_stages[0])):
            style = table_header_style if r == 0 else table_body_style
            pipeline_stages[r][c] = Paragraph(pipeline_stages[r][c], style)
            
    story.append(p_table)
    story.append(Spacer(1, 8))
    
    # ------------------ SECTIONS 2 & 3: CANONICAL SCHEMA & MERGE POLICY (Two columns) ------------------
    # Left Column: Canonical Schema
    col1_flowables = [
        Paragraph("2. CANONICAL SCHEMA & NORMALIZATION", h1_style),
        Paragraph("Profiles are resolved to a strict internal canonical schema with standardized types and normalizations:", body_style),
        Spacer(1, 4)
    ]
    
    schema_rows = [
        ["Field Name", "Canonical Type", "Format Normalization Rules"],
        ["candidate_id", "string (SHA-256)", "Lowercase primary email hashed"],
        ["full_name", "string", "Normalized to Title Case"],
        ["emails", "string[]", "Lowercase standard RFC 5322"],
        ["phones", "string[]", "E.164 format (+CountryCodePrefix)"],
        ["location", "dict", "{city, region, country (ISO-2)}"],
        ["links", "dict", "{linkedin, github, portfolio[], other[]}"],
        ["headline", "string | null", "Stated resume headline / job title"],
        ["years_experience", "number | null", "Calculated programmatically"],
        ["skills", "skill_object[]", "Mapped to Unified Taxonomy ontology"],
        ["experience", "exp_object[]", "Start/End (YYYY-MM), overlaps unified"],
        ["education", "edu_object[]", "Institution, Degree, Field, End Year"],
        ["provenance", "prov_object[]", "Auditable record of winning source/method"],
        ["overall_confidence", "number", "Weighted field confidence average [0, 1]"]
    ]
    
    s_table = Table(schema_rows, colWidths=[70, 75, 130])
    s_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('BACKGROUND', (0,1), (-1,-1), light_bg),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
    ]))
    
    for r in range(len(schema_rows)):
        for c in range(len(schema_rows[0])):
            style = table_header_style if r == 0 else table_body_style
            schema_rows[r][c] = Paragraph(schema_rows[r][c], style)
            
    col1_flowables.append(s_table)
    
    # Right Column: Merge / Arbitration & Confidence Policy
    col2_flowables = [
        Paragraph("3. MERGE, ARBITRATION & CONFIDENCE POLICIES", h1_style),
        Paragraph("<b>Profile Matching:</b> Duplicate sources are grouped by matching normalized primary email hashes.", body_style),
        Spacer(1, 3),
        Paragraph("<b>Source Confidence Baseline:</b>", body_style),
        Paragraph("• <i>Structured CSV Ingestion:</i> High baseline (0.95), directly parsed from ATS database exports.", bullet_style),
        Paragraph("• <i>Unstructured Resume Ingestion:</i> Contact details: 0.665; Experience/Education: 0.535; Prose body: 0.386.", bullet_style),
        Paragraph("• <i>Penalties:</i> Missing section structure deducts 0.15; nearly empty files (<50 chars) scale confidence by 0.30.", bullet_style),
        Spacer(1, 3),
        Paragraph("<b>Arbitration Strategies:</b>", body_style),
        Paragraph("• <i>Union Strategy (Lists):</i> Applied to emails, phones, skills, experience, and education. Duplicates are merged, and identical values gain a <b>+0.15 corroboration bonus</b>.", bullet_style),
        Paragraph("• <i>Highest Confidence (Singles):</i> Applied to name, location, and headline. The claim with the highest score wins.", bullet_style),
        Paragraph("• <i>Conflict Arbitration:</i> If two competing claims differ by a confidence margin <= 0.05, a conflict flag is raised in provenance metadata for downstream evaluation.", bullet_style),
        Spacer(1, 3),
        Paragraph("<b>Years of Experience Calculation:</b>", body_style),
        Paragraph("To prevent inflation, overlapping roles are merged using interval union arithmetic (projecting ranges onto a unified timeline) to calculate net non-overlapping work months.", body_style),
    ]
    
    # Place side-by-side in a layout table
    layout_data = [[col1_flowables, col2_flowables]]
    layout_table = Table(layout_data, colWidths=[281, 281])
    layout_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(layout_table)
    story.append(Spacer(1, 8))
    
    # ------------------ SECTION 4: RUNTIME PROJECTION & VALIDATION ------------------
    story.append(Paragraph("4. RUNTIME CONFIGURABLE PROJECTION & VALIDATION LAYER", h1_style))
    projection_desc = (
        "The engine maintains strict decoupling between the immutable <b>Canonical Profile</b> and the <b>Projection Layer</b>. "
        "At runtime, the transformer accepts a <b>ProjectionConfig</b> schema JSON, reshaping the output without code modifications. "
        "<b>Projection:</b> Flat or nested fields are mapped using dot-notation path selectors (e.g., <code>emails[0]</code> mapping to <code>primary_email</code>, "
        "<code>skills[].name</code> mapping to a flat skills list). "
        "<b>Validation:</b> Reshaped objects are run through a dynamic Pydantic Schema Validator. "
        "Missing fields are handled based on config instructions: <code>null</code> (insert null), <code>omit</code> (remove from payload), or <code>error</code> (raise validation exception)."
    )
    story.append(Paragraph(projection_desc, body_style))
    story.append(Spacer(1, 8))
    
    # ------------------ SECTION 5: RESILIENCY HEURISTICS & TIME-PRESSURE TRADE-OFFS ------------------
    story.append(Paragraph("5. INGESTION RESILIENCY DECISIONS & ARCHITECTURAL TRADE-OFFS", h1_style))
    
    resiliency_rows = [
        ["Ingestion Challenge", "Resilient Solution & Deterministic Heuristics", "Architectural Trade-offs & Scope Decisions"],
        ["Scanned & Image PDFs", "Scanned files (text < 100 chars) are routed to a layout-aware OCR fallback pipeline using pdfplumber page renders and pytesseract OCR.", "Requires tesseract-ocr binaries; raw images (PNG/JPG) are descoped, requiring conversion to PDF first."],
        ["Ambiguous Timeline Dates", "Translates timeline keywords ('Present', 'Current', 'Now') to runtime execution date; supports parsing fractional years and single-year ranges (e.g. 2022-2024).", "Stated experience numbers on resumes are ignored in favor of programmatically calculated values from interval union math."],
        ["Taxonomy Variations", "Aligns messy variations (e.g. 'py', 'js', 'Excel') using a standardized Skills Taxonomy ontology with exact, alias, and fuzzy-matching (rapidfuzz ratio > 85).", "Prose scans only accept exact/alias taxonomy matches, discarding fuzzy tokens to prevent false-positives in narrative text."],
        ["Corrupt & Missing Files", "Handles empty files, missing paths, and column mismatches gracefully by recording warnings in the pipeline metadata and outputting empty profiles.", "Operates on the core design principle: <i>'wrong-but-confident data is worse than honestly-empty'</i>; we fail safe rather than guess."],
        ["System Scale & Speed", "Applies section-aware regex parsing to limit token scan boundaries. Standardizes structures cleanly for concurrent processing.", "Named Entity Recognition (NER) models were descoped for deterministic section-aware regex matching to guarantee speed and 100% predictable output."]
    ]
    
    r_table = Table(resiliency_rows, colWidths=[100, 236, 236])
    r_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BACKGROUND', (0,1), (-1,-1), light_bg),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
    ]))
    
    for r in range(len(resiliency_rows)):
        for c in range(len(resiliency_rows[0])):
            style = table_header_style if r == 0 else table_body_style
            resiliency_rows[r][c] = Paragraph(resiliency_rows[r][c], style)
            
    story.append(r_table)
    
    # Render the PDF
    doc.build(story)
    print("PDF Successfully generated.")

if __name__ == "__main__":
    generate_pdf()
