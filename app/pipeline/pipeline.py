"""Orchestrator pipeline module wiring together all stages from detection to projection and validation."""

import os
import json
import logging
import traceback
from typing import Optional

from app.pipeline.models import ProjectionConfig, NormalizationStatus
from app.pipeline.source_detector import SourceDetector
from app.pipeline.extractors.csv_extractor import CSVExtractor
from app.pipeline.extractors.resume_extractor import ResumeExtractor
from app.pipeline.normalizer import Normalizer
from app.pipeline.arbitration import EvidenceArbitrationEngine
from app.pipeline.canonical_builder import CanonicalCandidateBuilder
from app.pipeline.projector import ProjectionEngine
from app.pipeline.validator import SchemaValidator

# Setup logger
logger = logging.getLogger(__name__)


class CandidateTransformerPipeline:
    """The central orchestrator that guides candidate documents through detection, extraction, normalizations, and validation."""

    def __init__(self, taxonomy_path: str = "data/skills_taxonomy.json") -> None:
        """Initializes all sub-modules and loads the skills taxonomy JSON ontology."""
        # 1. Resolve taxonomy_path dynamically to handle varying current working directories robustly
        self.taxonomy = {}
        possible_paths = [
            taxonomy_path,
            os.path.join(os.path.dirname(__file__), "..", "..", taxonomy_path),
            os.path.join(os.path.dirname(__file__), "..", "data", "skills_taxonomy.json"),
            os.path.join("candidate-transformer", taxonomy_path)
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        self.taxonomy = json.load(f)
                    logger.info(f"Orchestrator successfully loaded skills taxonomy from: {path}")
                    break
                except Exception as e:
                    logger.error(f"Failed to load taxonomy from path {path}: {e}")

        # 2. Instantiate pipeline processing components
        self.source_detector = SourceDetector()
        self.csv_extractor = CSVExtractor()
        self.resume_extractor = ResumeExtractor()
        self.normalizer = Normalizer(self.taxonomy)
        self.arbitration_engine = EvidenceArbitrationEngine()
        self.builder = CanonicalCandidateBuilder()
        self.projector = ProjectionEngine(self.taxonomy)
        self.validator = SchemaValidator()
        
        self.pipeline_log: list[dict] = []

    def log_step(self, step_name: str, details: str) -> None:
        """Appends progress log entries for tracking by downstream UIs or logs."""
        self.pipeline_log.append({
            "step": step_name,
            "details": details
        })

    def run(self, csv_path: Optional[str] = None, resume_path: Optional[str] = None, config_path: Optional[str] = None) -> dict:
        """Runs candidate profiles through the full ingestion pipeline with try-except fallback layers."""
        self.pipeline_log = []
        self.log_step("Pipeline Started", f"CSV path: {csv_path}, Resume path: {resume_path}, Config path: {config_path}")
        
        try:
            # Step 1: Validate Inputs
            self.log_step("Step 1: Input Validation", "Checking that at least one source file is provided.")
            if not csv_path and not resume_path:
                err_msg = "Invalid input: Neither csv_path nor resume_path was provided."
                self.log_step("Step 1 Failed", err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "traceback": ""
                }
            self.log_step("Step 1 Success", "Inputs validated.")

            # Step 2: Source Detection
            self.log_step("Step 2: Source Detection", "Detecting file types using python-magic and pdfplumber.")
            csv_meta = None
            resume_meta = None
            
            if csv_path:
                try:
                    csv_meta = self.source_detector.detect(csv_path)
                    self.log_step("CSV Source Detected", f"Type: {csv_meta['detected_type']}, Readable: {csv_meta['readable']}")
                except Exception as e:
                    self.log_step("CSV Source Detection Failed", str(e))
                    csv_meta = {"readable": False, "detected_type": "unknown", "warning": f"Detection error: {str(e)}", "file_name": os.path.basename(csv_path)}

            if resume_path:
                try:
                    resume_meta = self.source_detector.detect(resume_path)
                    self.log_step("Resume Source Detected", f"Type: {resume_meta['detected_type']}, Readable: {resume_meta['readable']}")
                except Exception as e:
                    self.log_step("Resume Source Detection Failed", str(e))
                    resume_meta = {"readable": False, "detected_type": "unknown", "warning": f"Detection error: {str(e)}", "file_name": os.path.basename(resume_path)}

            # Step 3: Extract Claims
            self.log_step("Step 3: Claims Extraction", "Extracting values as un-normalized evidence claims.")
            all_claims = []
            sources_processed = []
            all_warnings = []

            # Process CSV Ingestion
            if csv_path and csv_meta:
                if csv_meta["readable"] and csv_meta["detected_type"] == "csv":
                    if csv_meta.get("warning"):
                        all_warnings.append(csv_meta["warning"])
                    try:
                        claims = self.csv_extractor.extract(csv_path)
                        all_claims.extend(claims)
                        warnings = self.csv_extractor.get_warnings()
                        all_warnings.extend(warnings)
                        sources_processed.append(csv_meta["file_name"])
                        self.log_step("CSV Extraction Completed", f"Extracted {len(claims)} claims. Warnings: {len(warnings)}")
                    except Exception as e:
                        warn_msg = f"CSV extraction failed for {csv_path}: {e}"
                        logger.error(warn_msg)
                        all_warnings.append(warn_msg)
                        self.log_step("CSV Extraction Exception", str(e))
                else:
                    warn = csv_meta.get("warning") or f"CSV not readable or unsupported type: {csv_meta.get('detected_type')}"
                    all_warnings.append(warn)
                    self.log_step("CSV Extraction Skipped", warn)

            # Process Resume Ingestion
            if resume_path and resume_meta:
                det_type = resume_meta["detected_type"]
                if resume_meta["readable"] and det_type in ["pdf", "image_pdf", "docx"]:
                    if resume_meta.get("warning"):
                        all_warnings.append(resume_meta["warning"])
                    try:
                        claims = self.resume_extractor.extract(resume_path, det_type, self.taxonomy)
                        all_claims.extend(claims)
                        warnings = self.resume_extractor.get_warnings()
                        all_warnings.extend(warnings)
                        sources_processed.append(resume_meta["file_name"])
                        self.log_step("Resume Extraction Completed", f"Extracted {len(claims)} claims. Warnings: {len(warnings)}")
                    except Exception as e:
                        warn_msg = f"Resume extraction failed for {resume_path}: {e}"
                        logger.error(warn_msg)
                        all_warnings.append(warn_msg)
                        self.log_step("Resume Extraction Exception", str(e))
                else:
                    warn = resume_meta.get("warning") or f"Resume not readable or unsupported type: {det_type}"
                    all_warnings.append(warn)
                    self.log_step("Resume Extraction Skipped", warn)

            # Step 4: Normalization
            self.log_step("Step 4: Normalization", f"Running standardizing normalizers on {len(all_claims)} raw claims.")
            normalized_claims = []
            try:
                normalized_claims = self.normalizer.normalize(all_claims)
                self.log_step("Normalization Completed", f"Standardized {len(normalized_claims)} claims.")
                
                # Check for normalization failures
                for c in normalized_claims:
                    if c.normalization_status == NormalizationStatus.FAILED:
                        if c.field == "phone":
                            all_warnings.append(f"Phone normalization failed for value '{c.raw_value}'")
                        elif c.field == "email":
                            all_warnings.append(f"Email normalization failed for value '{c.raw_value}'")
                        else:
                            all_warnings.append(f"{c.field.title()} normalization failed for value '{c.raw_value}'")
            except Exception as e:
                warn_msg = f"Normalization layer encountered an error: {e}"
                logger.error(warn_msg)
                all_warnings.append(warn_msg)
                normalized_claims = all_claims
                self.log_step("Normalization Exception", str(e))

            # Step 5: Arbitration
            self.log_step("Step 5: Arbitration", "Arbitrating claims across sources to produce canonical values.")
            arbitrated_values = {}
            provenance = []
            try:
                arbitrated_values, provenance = self.arbitration_engine.arbitrate(normalized_claims)
                self.log_step("Arbitration Completed", f"Resolved {len(arbitrated_values)} canonical fields.")
            except Exception as e:
                logger.error(f"Arbitration engine error: {e}")
                self.log_step("Arbitration Exception", str(e))
                raise e

            # Step 6: Build Canonical
            self.log_step("Step 6: Build Canonical Record", "Constructing final CanonicalCandidate model and generating ID.")
            canonical_dict = {}
            run_timestamp = ""
            try:
                canonical = self.builder.build(arbitrated_values, provenance, sources_processed, all_warnings)
                run_timestamp = canonical.pipeline_run_timestamp
                canonical_dict = self.builder.to_dict(canonical)
                self.log_step("Canonical Record Built", f"Candidate ID: {canonical.candidate_id}")
            except Exception as e:
                logger.error(f"Canonical builder error: {e}")
                self.log_step("Canonical Build Exception", str(e))
                raise e

            # Step 7: Load Config
            self.log_step("Step 7: Load Config", "Loading ProjectionConfig schema overrides.")
            config = None
            try:
                if config_path:
                    config = self.projector.load_config(config_path)
                else:
                    config = ProjectionConfig(fields=[], include_confidence=True, include_provenance=True, on_missing="null")
                self.log_step("Config Loaded", "Configuration resolved.")
            except Exception as e:
                logger.error(f"Config load error: {e}")
                config = ProjectionConfig(fields=[], include_confidence=True, include_provenance=True, on_missing="null")
                self.log_step("Config Exception (Using Fallback)", str(e))

            # Step 8: Project
            self.log_step("Step 8: Projection", "Reshaping canonical profile to custom configuration format.")
            projected = {}
            try:
                projected = self.projector.project(canonical_dict, config)
                self.log_step("Projection Completed", "Reshaping done.")
            except Exception as e:
                logger.error(f"Projector error: {e}")
                projected = canonical_dict
                self.log_step("Projection Exception (Using Canonical Fallback)", str(e))

            # Step 9: Validate
            self.log_step("Step 9: Validation", "Validating output against expectations.")
            result = None
            try:
                result = self.validator.validate(projected, config)
                self.log_step("Validation Completed", f"Valid: {result.valid}, Errors: {len(result.errors)}, Warnings: {len(result.warnings)}")
            except Exception as e:
                logger.error(f"Validator error: {e}")
                from app.pipeline.models import ValidationResult
                result = ValidationResult(valid=False, errors=[{"field": "pipeline", "error": str(e), "value": None}], warnings=[], projected_output=projected)
                self.log_step("Validation Exception", str(e))

            # Step 10: Return Final Result
            self.log_step("Pipeline Completed Successfully", "Returning aggregated pipeline payload.")
            return {
                "success": True,
                "canonical": canonical_dict,
                "projected": result.projected_output,
                "validation": {
                    "valid": result.valid,
                    "errors": result.errors,
                    "warnings": result.warnings
                },
                "pipeline_meta": {
                    "sources_processed": sources_processed,
                    "all_warnings": all_warnings,
                    "pipeline_run_timestamp": run_timestamp,
                    "pipeline_log": self.pipeline_log
                }
            }

        except Exception as e:
            tb = traceback.format_exc()
            logger.critical(f"Unhandled exception in pipeline run: {e}\n{tb}")
            self.log_step("Pipeline Crashed", f"Error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "traceback": tb,
                "pipeline_meta": {
                    "sources_processed": [],
                    "all_warnings": [f"Pipeline crashed: {str(e)}"],
                    "pipeline_run_timestamp": "",
                    "pipeline_log": self.pipeline_log
                }
            }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the Candidate Transformer pipeline.")
    parser.add_argument("--csv", help="Path to structured CSV file")
    parser.add_argument("--resume", help="Path to unstructured resume file")
    parser.add_argument("--config", help="Path to JSON projection config file")
    args = parser.parse_args()

    pipeline = CandidateTransformerPipeline()
    res = pipeline.run(csv_path=args.csv, resume_path=args.resume, config_path=args.config)
    print(json.dumps(res, indent=2))
