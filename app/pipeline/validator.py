"""Validator module to check projected outputs against expected schemas."""

import re
import logging

from app.pipeline.models import ValidationResult, ProjectionConfig

# Setup logger
logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates structural and type integrity of projected candidate documents."""

    def __init__(self) -> None:
        """Initializes the SchemaValidator instance."""
        pass

    def validate(self, projected_output: dict, config: ProjectionConfig) -> ValidationResult:
        """Validates the output document based on default schema or field specification mapping rules."""
        errors: list[dict] = []
        warnings: list[str] = []

        # 1. If config fields are empty → validate against the default schema
        if not config.fields:
            # Required fields: candidate_id (string), emails (list), overall_confidence (number 0-1)
            # Candidate ID
            if "candidate_id" not in projected_output:
                errors.append({"field": "candidate_id", "error": "Required field is missing.", "value": None})
            elif not isinstance(projected_output["candidate_id"], str):
                errors.append({"field": "candidate_id", "error": "Must be a string.", "value": projected_output["candidate_id"]})

            # Emails
            if "emails" not in projected_output:
                errors.append({"field": "emails", "error": "Required field is missing.", "value": None})
            elif not isinstance(projected_output["emails"], list):
                errors.append({"field": "emails", "error": "Must be a list.", "value": projected_output["emails"]})

            # Overall Confidence (required in default schema unless stripped by config flags)
            if "overall_confidence" not in projected_output:
                if config.include_confidence:
                    errors.append({"field": "overall_confidence", "error": "Required field is missing.", "value": None})
            else:
                conf = projected_output["overall_confidence"]
                if not isinstance(conf, (int, float)):
                    errors.append({"field": "overall_confidence", "error": "Must be a number.", "value": conf})
                elif not (0.0 <= conf <= 1.0):
                    errors.append({"field": "overall_confidence", "error": "Must be between 0.0 and 1.0.", "value": conf})

            # Optional fields type checks
            # Full Name
            if "full_name" in projected_output:
                fn = projected_output["full_name"]
                if fn is not None and not isinstance(fn, str):
                    errors.append({"field": "full_name", "error": "Must be a string or null.", "value": fn})

            # Phones
            if "phones" in projected_output:
                ph = projected_output["phones"]
                if ph is not None and not isinstance(ph, list):
                    errors.append({"field": "phones", "error": "Must be a list.", "value": ph})

            # Location Dict
            if "location" in projected_output:
                loc = projected_output["location"]
                if loc is not None:
                    if not isinstance(loc, dict):
                        errors.append({"field": "location", "error": "Must be a dictionary.", "value": loc})
                    else:
                        for key in ["city", "region", "country"]:
                            if key not in loc:
                                errors.append({"field": f"location.{key}", "error": f"Missing key: {key}", "value": loc})

            # Links Dict
            if "links" in projected_output:
                ln = projected_output["links"]
                if ln is not None:
                    if not isinstance(ln, dict):
                        errors.append({"field": "links", "error": "Must be a dictionary.", "value": ln})
                    else:
                        for key in ["linkedin", "github", "portfolio", "other"]:
                            if key not in ln:
                                errors.append({"field": f"links.{key}", "error": f"Missing key: {key}", "value": ln})

            # Headline
            if "headline" in projected_output:
                hl = projected_output["headline"]
                if hl is not None and not isinstance(hl, str):
                    errors.append({"field": "headline", "error": "Must be a string or null.", "value": hl})

            # Years Experience
            if "years_experience" in projected_output:
                ye = projected_output["years_experience"]
                if ye is not None:
                    if not isinstance(ye, (int, float)):
                        errors.append({"field": "years_experience", "error": "Must be a number or null.", "value": ye})
                    elif ye < 0:
                        errors.append({"field": "years_experience", "error": "Must be greater than or equal to 0.", "value": ye})

            # Skills
            if "skills" in projected_output:
                sk = projected_output["skills"]
                if sk is not None:
                    if not isinstance(sk, list):
                        errors.append({"field": "skills", "error": "Must be a list.", "value": sk})
                    else:
                        for idx, s in enumerate(sk):
                            if not isinstance(s, dict):
                                errors.append({"field": f"skills[{idx}]", "error": "Must be a dictionary.", "value": s})
                            else:
                                for key in ["name", "confidence", "sources"]:
                                    if key not in s:
                                        errors.append({"field": f"skills[{idx}].{key}", "error": f"Missing key: {key}", "value": s})

            # Experience
            if "experience" in projected_output:
                exp = projected_output["experience"]
                if exp is not None:
                    if not isinstance(exp, list):
                        errors.append({"field": "experience", "error": "Must be a list.", "value": exp})
                    else:
                        for idx, entry in enumerate(exp):
                            if not isinstance(entry, dict):
                                errors.append({"field": f"experience[{idx}]", "error": "Must be a dictionary.", "value": entry})
                            else:
                                for key in ["company", "title", "start", "end", "summary"]:
                                    if key not in entry:
                                        errors.append({"field": f"experience[{idx}].{key}", "error": f"Missing key: {key}", "value": entry})

            # Education
            if "education" in projected_output:
                edu = projected_output["education"]
                if edu is not None:
                    if not isinstance(edu, list):
                        errors.append({"field": "education", "error": "Must be a list.", "value": edu})
                    else:
                        for idx, entry in enumerate(edu):
                            if not isinstance(entry, dict):
                                errors.append({"field": f"education[{idx}]", "error": "Must be a dictionary.", "value": entry})
                            else:
                                for key in ["institution", "degree", "field", "end_year"]:
                                    if key not in entry:
                                        errors.append({"field": f"education[{idx}].{key}", "error": f"Missing key: {key}", "value": entry})

            # Provenance
            if "provenance" in projected_output:
                prov = projected_output["provenance"]
                if prov is not None and not isinstance(prov, list):
                    errors.append({"field": "provenance", "error": "Must be a list.", "value": prov})

            # Pipeline Run Timestamp
            if "pipeline_run_timestamp" in projected_output:
                ts = projected_output["pipeline_run_timestamp"]
                if ts is not None and not isinstance(ts, str):
                    errors.append({"field": "pipeline_run_timestamp", "error": "Must be a string.", "value": ts})

        # 2. If config.fields is provided → validate required projection mapping keys exist
        else:
            for field_spec in config.fields:
                path = field_spec.get("path")
                required = field_spec.get("required", False)
                if required:
                    if path not in projected_output or projected_output[path] is None:
                        errors.append({
                            "field": path,
                            "error": f"Required mapped field is missing or resolved to null.",
                            "value": projected_output.get(path)
                        })

        # 3. Non-fatal Warnings checks
        # overall_confidence checks
        if "overall_confidence" in projected_output:
            conf = projected_output["overall_confidence"]
            if conf is not None:
                try:
                    if float(conf) < 0.5:
                        warnings.append(f"Low overall confidence: {conf}. Profile may be incomplete.")
                except (ValueError, TypeError):
                    pass

        # years_experience checks
        if "years_experience" in projected_output:
            ye = projected_output["years_experience"]
            if ye is not None:
                try:
                    if float(ye) > 50:
                        warnings.append(f"Unusually high years_experience: {ye}. Verify date ranges.")
                except (ValueError, TypeError):
                    pass

        # empty emails checks
        if "emails" in projected_output:
            emails = projected_output["emails"]
            if isinstance(emails, list) and len(emails) == 0:
                warnings.append("No email found. candidate_id may be unreliable.")

        # empty skills checks
        if "skills" in projected_output:
            skills = projected_output["skills"]
            if isinstance(skills, list) and len(skills) == 0:
                warnings.append("No skills extracted.")

        # phone formatting checks
        if "phones" in projected_output:
            phones = projected_output["phones"]
            if isinstance(phones, list):
                for phone in phones:
                    if not re.match(r'^\+\d{7,15}$', str(phone)):
                        warnings.append(f"Phone not in E.164 format: {phone}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            projected_output=projected_output
        )
