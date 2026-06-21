"""Routes definitions and controller functions for web UI and API endpoints."""

import os
import json
import logging
import tempfile
from flask import Blueprint, request, jsonify, render_template
from werkzeug.utils import secure_filename
from pydantic import ValidationError

from app.pipeline.pipeline import CandidateTransformerPipeline
from app.pipeline.models import ProjectionConfig

# Setup logger
logger = logging.getLogger(__name__)

# Declare main Blueprint
main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """GET /: Renders the home page of the candidate transformer application UI."""
    try:
        return render_template("index.html", title="Candidate Transformer")
    except Exception as e:
        logger.error(f"Error rendering index template: {e}")
        return jsonify({"success": False, "error": "Index template rendering failed."}), 500


@main_bp.route("/run", methods=["POST"])
def run_pipeline():
    """POST /run: Executes candidate ingestion pipelines on CSV and resume file inputs."""
    csv_file = request.files.get("csv_file")
    resume_file = request.files.get("resume_file")
    config_str = request.form.get("config")
    config_file = request.files.get("config_file")

    # Verify that at least one source file is uploaded
    if not (csv_file and csv_file.filename != '') and not (resume_file and resume_file.filename != ''):
        return jsonify({
            "success": False,
            "error": "No input files provided. Provide at least one of csv_file or resume_file."
        }), 400

    # Write files to a localized temporary directory and parse
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = None
        resume_path = None
        config_path = None

        if csv_file and csv_file.filename != '':
            csv_path = os.path.join(temp_dir, secure_filename(csv_file.filename))
            csv_file.save(csv_path)

        if resume_file and resume_file.filename != '':
            resume_path = os.path.join(temp_dir, secure_filename(resume_file.filename))
            resume_file.save(resume_path)

        # Handle config overrides
        if config_file and config_file.filename != '':
            config_path = os.path.join(temp_dir, "projection_config.json")
            config_file.save(config_path)
        elif config_str and config_str.strip():
            try:
                config_json = json.loads(config_str)
                config_path = os.path.join(temp_dir, "projection_config.json")
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_json, f)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Invalid config JSON string: {str(e)}"
                }), 400

        try:
            # Instantiate pipeline and execute
            pipeline = CandidateTransformerPipeline()
            res = pipeline.run(csv_path, resume_path, config_path)

            if res.get("success"):
                return jsonify({
                    "success": True,
                    "result": res,
                    "pipeline_log": res.get("pipeline_meta", {}).get("pipeline_log", [])
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": res.get("error"),
                    "pipeline_log": res.get("pipeline_log", [])
                }), 500

        except Exception as e:
            logger.exception("Pipeline run crashed in route execution.")
            return jsonify({
                "success": False,
                "error": f"Pipeline execution crashed: {str(e)}"
            }), 500


@main_bp.route("/api/schema", methods=["GET"])
def get_schema():
    """GET /api/schema: Returns canonical dictionary format definitions for UIs."""
    schema = {
        "candidate_id": "string (SHA-256 hash of email)",
        "full_name": "string (Title cased)",
        "emails": "array of strings (RFC 5322 valid)",
        "phones": "array of strings (E.164 format)",
        "location": "object {city: string, region: string, country: string (ISO-2-letter)}",
        "links": "object {linkedin: string, github: string, portfolio: array of strings, other: array of strings}",
        "headline": "string",
        "years_experience": "number (reconstructed from date intervals)",
        "skills": "array of objects [{name: string, confidence: float, sources: array of strings}]",
        "experience": "array of objects [{company: string, title: string, start: string (YYYY-MM), end: string (YYYY-MM or null), summary: string, concurrent: boolean, sources: array of strings, confidence: float}]",
        "education": "array of objects [{institution: string, degree: string, field: string, end_year: integer, sources: array of strings, confidence: float}]",
        "overall_confidence": "number (weighted field score 0-1)",
        "pipeline_run_timestamp": "string (ISO-8601 Zulu format)"
    }
    return jsonify(schema), 200


@main_bp.route("/api/sample-config", methods=["GET"])
def get_sample_config():
    """GET /api/sample-config: Provides reference schemas for output projections."""
    sample_configs = {
        "default": {
            "fields": [],
            "include_confidence": True,
            "include_provenance": True,
            "on_missing": "null"
        },
        "custom": {
            "fields": [
                {"path": "full_name", "type": "string", "required": True},
                {"path": "primary_email", "from": "emails[0]", "type": "string", "required": True},
                {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
                {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
            ],
            "include_confidence": True,
            "include_provenance": False,
            "on_missing": "null"
        }
    }
    return jsonify(sample_configs), 200


@main_bp.route("/api/validate-config", methods=["POST"])
def validate_config():
    """POST /api/validate-config: Validates a user-provided ProjectionConfig representation."""
    data = request.json or {}
    try:
        # Step 1: Validate against Pydantic schema
        ProjectionConfig(**data)

        # Step 2: Validate nested field details
        errors = []
        for idx, field in enumerate(data.get("fields", [])):
            if not isinstance(field, dict):
                errors.append(f"fields[{idx}] must be a JSON object.")
                continue
            if "path" not in field:
                errors.append(f"fields[{idx}] is missing the required key 'path'.")
            if "type" not in field:
                errors.append(f"fields[{idx}] is missing the required key 'type'.")
            elif field["type"] not in ["string", "string[]", "number", "boolean"]:
                errors.append(f"fields[{idx}] contains an invalid type value: '{field['type']}'.")

        on_missing = data.get("on_missing", "null")
        if on_missing not in ["null", "omit", "error"]:
            errors.append(f"invalid value for 'on_missing': '{on_missing}'.")

        if errors:
            return jsonify({"valid": False, "errors": errors}), 200

        return jsonify({"valid": True, "errors": []}), 200

    except ValidationError as e:
        # Map Pydantic errors to user-friendly messages
        errors = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        return jsonify({"valid": False, "errors": errors}), 200
    except Exception as e:
        return jsonify({"valid": False, "errors": [str(e)]}), 200
