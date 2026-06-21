"""Projector module to shape and query canonical candidates to custom schemas at runtime.

SAMPLE CONFIGS:

1. DEFAULT CONFIG (returns all fields as-is):
{
  "fields": [],
  "include_confidence": true,
  "include_provenance": true,
  "on_missing": "null"
}

2. CUSTOM CONFIG (resolves subset of fields, swaps paths, normalizes):
{
  "fields": [
    {"path": "full_name", "type": "string", "required": true},
    {"path": "primary_email", "from": "emails[0]", "type": "string", "required": true},
    {"path": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
    {"path": "skills", "from": "skills[].name", "type": "string[]", "normalize": "canonical"}
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
"""

import json
import logging
from typing import Any

from app.pipeline.models import ProjectionConfig
from app.pipeline.normalizer import Normalizer

# Setup logger
logger = logging.getLogger(__name__)


class ProjectionError(Exception):
    """Exception raised when a projection path cannot be resolved and required field is missing."""
    pass


class ProjectionEngine:
    """Pure-function projection engine to reshape canonical profiles into target formats dynamically."""

    def __init__(self, taxonomy: dict = None) -> None:
        """Initializes the ProjectionEngine with a skills taxonomy dictionary."""
        self.taxonomy = taxonomy or {}
        # Instantiate normalizer to support re-normalization requests during projection
        self.normalizer = Normalizer(self.taxonomy)

    def _get_nested_value(self, data: Any, parts: list[str]) -> Any:
        """Resolves deep value mappings using recursion and array-slicing syntax."""
        if not parts:
            return data
        if data is None:
            return None

        part = parts[0]
        remaining = parts[1:]

        # Handle list mapping syntax e.g. "skills[].name"
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(data, dict) or key not in data:
                return None
            lst = data[key]
            if not isinstance(lst, list):
                return None
            # Recursively apply path remainder to each list item
            return [self._get_nested_value(item, remaining) for item in lst]

        # Handle list index mapping syntax e.g. "emails[0]"
        elif "[" in part and part.endswith("]"):
            key = part.split("[")[0]
            idx_str = part.split("[")[1][:-1]
            try:
                idx = int(idx_str)
            except ValueError:
                return None

            if key:
                if not isinstance(data, dict) or key not in data:
                    return None
                lst = data[key]
            else:
                lst = data

            if not isinstance(lst, list) or idx < 0 or idx >= len(lst):
                return None
            return self._get_nested_value(lst[idx], remaining)

        # Handle direct key mapping
        else:
            if not isinstance(data, dict) or part not in data:
                return None
            return self._get_nested_value(data[part], remaining)

    def _normalize_value(self, val: Any, method: str) -> Any:
        """Applies normalization formats to mapped values."""
        if val is None:
            return None

        # Recursively normalize list items if value represents a list
        if isinstance(val, list):
            return [self._normalize_value(item, method) for item in val]

        if method == "lowercase":
            return str(val).lower()

        elif method == "E164":
            norm_val, status, _, _ = self.normalizer._normalize_phone(str(val))
            return norm_val if norm_val else val

        elif method == "canonical":
            norm_val, status, _, _ = self.normalizer._normalize_skill(str(val), self.taxonomy)
            return norm_val if norm_val else val

        elif method == "iso3166":
            norm_val, status, _, _ = self.normalizer._normalize_country(str(val))
            return norm_val if norm_val else val

        return val

    def _coerce_type(self, val: Any, expected_type: str) -> Any:
        """Coerces the value to the target type."""
        if val is None:
            return None

        if expected_type == "string":
            return str(val)

        elif expected_type == "string[]":
            if isinstance(val, list):
                return [str(item) for item in val if item is not None]
            return [str(val)]

        elif expected_type == "number":
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        elif expected_type == "boolean":
            return bool(val)

        return val

    def project(self, canonical_dict: dict, config: ProjectionConfig) -> dict:
        """Reshapes the CanonicalCandidate dict using custom ProjectionConfig rules."""
        # Rule 1: If config fields are empty, return the entire dictionary as-is
        if not config.fields:
            output = dict(canonical_dict)
        else:
            output = {}
            for field_spec in config.fields:
                path = field_spec.get("path")
                # Rule 2: If "from" path is omitted, default "from" to the target "path" key name
                from_path = field_spec.get("from") or path
                expected_type = field_spec.get("type", "string")
                required = field_spec.get("required", False)
                norm_method = field_spec.get("normalize")

                # Split path by dot token separators
                parts = from_path.split(".")
                
                # Rule 3: Resolve deep value from dict
                raw_val = self._get_nested_value(canonical_dict, parts)

                # Rule 5: Handle Missing Value Conditions
                if raw_val is None:
                    if required:
                        raise ProjectionError(f"Required field '{path}' (mapped from '{from_path}') is missing or null.")
                    
                    if config.on_missing == "error":
                        raise ProjectionError(f"Missing field mapping '{path}' from path '{from_path}' under error policy.")
                    elif config.on_missing == "omit":
                        continue
                    else:
                        output[path] = None
                        continue

                # Rule 4: Apply Normalization
                if norm_method:
                    raw_val = self._normalize_value(raw_val, norm_method)

                # Rule 6: Type Coercion
                coerced_val = self._coerce_type(raw_val, expected_type)

                # Rule 7: Populate target output
                output[path] = coerced_val

        # Rule 8: If include_confidence is False, strip out overall_confidence and skill confidence scores
        if not config.include_confidence:
            output.pop("overall_confidence", None)
            if "skills" in output and isinstance(output["skills"], list):
                cleaned_skills = []
                for s in output["skills"]:
                    if isinstance(s, dict):
                        s_copy = dict(s)
                        s_copy.pop("confidence", None)
                        cleaned_skills.append(s_copy)
                    else:
                        cleaned_skills.append(s)
                output["skills"] = cleaned_skills
        else:
            if "overall_confidence" not in output and "overall_confidence" in canonical_dict:
                output["overall_confidence"] = canonical_dict["overall_confidence"]

        # Rule 9: If include_provenance is False, strip out audit trails
        if not config.include_provenance:
            output.pop("provenance", None)
        else:
            if "provenance" not in output and "provenance" in canonical_dict:
                if config.fields:
                    referenced_fields = self._get_referenced_canonical_fields(config.fields)
                    filtered_provenance = [
                        prov for prov in canonical_dict["provenance"]
                        if isinstance(prov, dict) and prov.get("field") in referenced_fields
                    ]
                    output["provenance"] = filtered_provenance
                else:
                    output["provenance"] = canonical_dict["provenance"]

        return output

    def _get_referenced_canonical_fields(self, fields: list[dict]) -> set[str]:
        """Identifies which canonical fields are referenced by the custom projection configuration fields."""
        referenced = set()
        for field_spec in fields:
            path = field_spec.get("path", "")
            from_path = field_spec.get("from") or path
            if not from_path:
                continue
            
            from_path_lower = from_path.lower()
            
            if "email" in from_path_lower:
                referenced.add("email")
            if "phone" in from_path_lower:
                referenced.add("phone")
            if "linkedin" in from_path_lower:
                referenced.add("linkedin_url")
            if "github" in from_path_lower:
                referenced.add("github_url")
            if "portfolio" in from_path_lower:
                referenced.add("portfolio_url")
            if "full_name" in from_path_lower:
                referenced.add("full_name")
            if "headline" in from_path_lower:
                referenced.add("headline")
            if "location" in from_path_lower:
                referenced.add("location")
            if "current_company" in from_path_lower or "experience[0].company" in from_path_lower:
                referenced.add("current_company")
            if "skills" in from_path_lower:
                referenced.add("skills")
            if "experience" in from_path_lower:
                if "company" in from_path_lower:
                    referenced.add("current_company")
                else:
                    referenced.add("experience")
                    referenced.add("years_experience")
            if "education" in from_path_lower:
                referenced.add("education")
            if "years_experience" in from_path_lower:
                referenced.add("years_experience")
            if "links" in from_path_lower:
                if "linkedin" in from_path_lower:
                    referenced.add("linkedin_url")
                elif "github" in from_path_lower:
                    referenced.add("github_url")
                elif "portfolio" in from_path_lower:
                    referenced.add("portfolio_url")
                else:
                    referenced.update(["linkedin_url", "github_url", "portfolio_url"])
                
        return referenced

    def load_config(self, config_path: str) -> ProjectionConfig:
        """Loads a ProjectionConfig instance from a JSON configuration file path."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return ProjectionConfig(**data)
        except FileNotFoundError:
            logger.warning(f"Configuration file not found at {config_path}. Reverting to default pass-through config.")
            return ProjectionConfig(fields=[], include_confidence=True, include_provenance=True, on_missing="null")
        except Exception as e:
            logger.error(f"Error parsing ProjectionConfig at {config_path}: {e}. Reverting to default config.")
            return ProjectionConfig(fields=[], include_confidence=True, include_provenance=True, on_missing="null")
