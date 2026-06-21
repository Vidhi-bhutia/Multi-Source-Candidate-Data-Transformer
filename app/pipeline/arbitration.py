"""Arbitration engine to resolve conflicts across candidate claims and build canonical records."""

import re
import logging
from typing import Any

from app.pipeline.models import (
    Claim,
    SkillClaim,
    ExperienceEntry,
    EducationEntry,
    ProvenanceRecord,
    SourceType,
    NormalizationStatus
)

# Setup logging
logger = logging.getLogger(__name__)

# Field weights for computing overall pipeline confidence score
FIELD_WEIGHTS = {
    "email": 0.20,
    "phone": 0.10,
    "full_name": 0.15,
    "headline": 0.10,
    "skills": 0.20,
    "experience": 0.15,
    "education": 0.10
}


class EvidenceArbitrationEngine:
    """Arbitrates competing candidate claims across multiple data sources to produce a single canonical profile."""

    def __init__(self, run_timestamp: str = "2026-06-20T17:22:36Z") -> None:
        """Initializes the arbitration engine with the run timestamp."""
        self.run_timestamp = run_timestamp

    def _are_claims_equal(self, claim1: Claim, claim2: Claim) -> bool:
        """Checks if two claims for the same field have equivalent normalized values."""
        val1 = claim1.normalized_value
        val2 = claim2.normalized_value

        if val1 is None or val2 is None:
            return False

        field = claim1.field

        if field == "email":
            return str(val1).strip().lower() == str(val2).strip().lower()

        if field == "phone":
            # Compare formatted E.164 strings directly
            return str(val1).strip() == str(val2).strip()

        if field == "full_name":
            return str(val1).strip().lower() == str(val2).strip().lower()

        if field in ["linkedin_url", "github_url", "portfolio_url"]:
            # Perform lowercase comparison stripping any trailing slashes
            u1 = str(val1).strip().lower().rstrip('/')
            u2 = str(val2).strip().lower().rstrip('/')
            return u1 == u2

        # Default fallback exact comparison
        return val1 == val2

    def _normalize_month(self, m_str: str) -> str:
        """Translates month name string to a two-digit month representation ('01'-'12')."""
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

    def _parse_year_month(self, date_str: str | None, is_end: bool = False) -> tuple[int, int]:
        """Parses a date string into a tuple of (year, month), falling back to run timestamp if blank."""
        if not date_str or date_str.lower() in ["present", "current", "now", "ongoing"]:
            try:
                # Parse timestamp date segment
                match = re.match(r'^(\d{4})\-(\d{2})', self.run_timestamp)
                if match:
                    return int(match.group(1)), int(match.group(2))
            except Exception:
                pass
            return 2026, 6  # Default fallback if parsing fails

        parts = date_str.split('-')
        try:
            year = int(parts[0])
            # Default to month 12 for end dates, month 1 for start dates if month is missing
            month = int(parts[1]) if len(parts) > 1 else (12 if is_end else 1)
            return year, month
        except Exception:
            return 2026, 6

    def _is_same_role(self, e1: ExperienceEntry, e2: ExperienceEntry) -> bool:
        """Determines if two ExperienceEntry objects refer to the same job role."""
        if not e1.company or not e2.company:
            return False

        # Clean company names to eliminate spelling suffixes like Inc or LLC
        c1 = re.sub(r'\b(inc|llc|ltd|corp|solutions|technologies)\b', '', e1.company, flags=re.IGNORECASE).strip().lower()
        c2 = re.sub(r'\b(inc|llc|ltd|corp|solutions|technologies)\b', '', e2.company, flags=re.IGNORECASE).strip().lower()

        # Company match: exact, or one is a substring of the other
        if c1 != c2 and c1 not in c2 and c2 not in c1:
            return False

        # Convert date range to cumulative integer months
        s1 = self._date_to_int(e1.start)
        e1_end = e1.end if e1.end else "Present"
        e1_val = self._date_to_int(e1_end)

        s2 = self._date_to_int(e2.start)
        e2_end = e2.end if e2.end else "Present"
        e2_val = self._date_to_int(e2_end)

        # Overlapping or adjacent check within a 1-month tolerance window
        return s1 <= (e2_val + 1) and s2 <= (e1_val + 1)

    def _merge_entries(self, e1: ExperienceEntry, e2: ExperienceEntry) -> ExperienceEntry:
        """Merges two matching ExperienceEntry blocks and increases confidence due to corroboration."""
        # Accumulate unique sources from both entries
        sources = list(set(e1.sources + e2.sources))

        # Select longer company name representation
        company = e1.company if (e1.company and len(e1.company) >= len(e2.company or "")) else e2.company

        # Select longer title representation
        title = e1.title if (e1.title and len(e1.title) >= len(e2.title or "")) else e2.title

        # Select first non-null date values
        start = e1.start if e1.start else e2.start
        end = e1.end if e1.end else e2.end

        # Join descriptions if they differ
        summaries = []
        if e1.summary:
            summaries.append(e1.summary)
        if e2.summary and e2.summary not in summaries:
            summaries.append(e2.summary)
        summary = " | ".join(summaries) if summaries else None

        # Increase confidence by 0.10 due to multi-source verification
        confidence = min(1.0, max(e1.confidence, e2.confidence) + 0.10)

        return ExperienceEntry(
            company=company,
            title=title,
            start=start,
            end=end,
            summary=summary,
            concurrent=e1.concurrent or e2.concurrent,
            sources=sources,
            confidence=confidence
        )

    def _strategy_union(self, claims: list[Claim], field: str) -> tuple[list, ProvenanceRecord]:
        """Union arbitration strategy: pools all unique normalized values across claims."""
        valid_claims = [c for c in claims if c.normalized_value is not None]

        if not valid_claims:
            provenance = ProvenanceRecord(
                field=field,
                winning_value=[],
                winning_source="none",
                winning_method="none",
                winning_confidence=0.0,
                resolution_strategy="union",
                all_claims=[c.model_dump() for c in claims],
                conflict_detected=False,
                transformation_applied=[]
            )
            return [], provenance

        # Deduplicate values case-insensitively for emails and URLs
        deduped_claims: list[Claim] = []
        seen = set()
        for c in valid_claims:
            val = c.normalized_value
            if field in ["email", "linkedin_url", "github_url", "portfolio_url"]:
                key = str(val).lower().strip().rstrip('/')
            else:
                key = str(val).strip()

            if key not in seen:
                seen.add(key)
                deduped_claims.append(c)
            else:
                # Merge source reference corroboration on existing entry
                existing = next(ec for ec in deduped_claims if (
                    str(ec.normalized_value).lower().strip().rstrip('/') 
                    if field in ["email", "linkedin_url", "github_url", "portfolio_url"] 
                    else str(ec.normalized_value).strip()) == key)
                if c.confidence > existing.confidence:
                    existing.confidence = c.confidence
                    existing.source = c.source
                    existing.extraction_method = c.extraction_method
                if c.source not in existing.corroborated_by:
                    existing.corroborated_by.append(c.source)

        # Sort claims descending by confidence score
        deduped_claims.sort(key=lambda x: x.confidence, reverse=True)

        winning_values = [c.normalized_value for c in deduped_claims]
        winner = deduped_claims[0]

        provenance = ProvenanceRecord(
            field=field,
            winning_value=winning_values,
            winning_source=winner.source,
            winning_method=winner.extraction_method.value,
            winning_confidence=winner.confidence,
            resolution_strategy="union",
            all_claims=[c.model_dump() for c in claims],
            conflict_detected=False,
            transformation_applied=[]
        )
        return winning_values, provenance

    def _strategy_highest_confidence(self, claims: list[Claim], field: str) -> tuple[Any, ProvenanceRecord]:
        """Highest-confidence arbitration: selects claim with highest score; resolves ties with structured priority."""
        valid_claims = [c for c in claims if c.normalized_value is not None]

        if not valid_claims:
            provenance = ProvenanceRecord(
                field=field,
                winning_value=None,
                winning_source="none",
                winning_method="none",
                winning_confidence=0.0,
                resolution_strategy="highest_confidence",
                all_claims=[c.model_dump() for c in claims],
                conflict_detected=False,
                transformation_applied=[]
            )
            return None, provenance

        # Find the maximum confidence score
        max_confidence = max(c.confidence for c in valid_claims)

        # Filter claims within 0.05 of the maximum confidence
        eligible_claims = [c for c in valid_claims if (max_confidence - c.confidence) <= 0.05]

        # Sort eligible claims to prefer STRUCTURED sources, then higher confidence
        eligible_claims.sort(key=lambda x: (1 if x.source_type == SourceType.STRUCTURED else 0, x.confidence), reverse=True)

        winner = eligible_claims[0]
        conflict_detected = False

        # Set conflict_detected if any other claim has a different value and is within 0.05 confidence bounds
        for c in valid_claims:
            if c != winner and c.normalized_value != winner.normalized_value:
                if abs(winner.confidence - c.confidence) <= 0.05:
                    conflict_detected = True
                    break

        provenance = ProvenanceRecord(
            field=field,
            winning_value=winner.normalized_value,
            winning_source=winner.source,
            winning_method=winner.extraction_method.value,
            winning_confidence=winner.confidence,
            resolution_strategy="highest_confidence",
            all_claims=[c.model_dump() for c in claims],
            conflict_detected=conflict_detected,
            transformation_applied=[]
        )
        return winner.normalized_value, provenance

    def _strategy_computed_years_experience(self, experience_entries: list[ExperienceEntry], all_claims: list[dict]) -> tuple[float | None, ProvenanceRecord]:
        """Years experience strategy: merges overlapping work intervals to compute net experience length."""
        intervals = []
        for entry in experience_entries:
            sy, sm = self._parse_year_month(entry.start, is_end=False)
            ey, em = self._parse_year_month(entry.end, is_end=True)
            s_val = sy * 12 + sm
            e_val = ey * 12 + em
            intervals.append([s_val, e_val])

        if not intervals:
            provenance = ProvenanceRecord(
                field="years_experience",
                winning_value=0.0,
                winning_source="computed",
                winning_method="computed",
                winning_confidence=0.92,
                resolution_strategy="computed_from_date_ranges",
                all_claims=all_claims,
                conflict_detected=False,
                transformation_applied=[]
            )
            return 0.0, provenance

        # Sort intervals by start date cumulative months
        intervals.sort(key=lambda x: x[0])

        # Merge overlapping date segments
        merged = []
        for interval in intervals:
            if not merged:
                merged.append(interval)
            else:
                last = merged[-1]
                # Check for overlap: interval start <= last interval end
                if interval[0] <= last[1]:
                    last[1] = max(last[1], interval[1])
                else:
                    merged.append(interval)

        # Sum total months (inclusive) across distinct intervals
        total_months = sum(e - s + 1 for s, e in merged)
        years = round(total_months / 12.0, 1)

        concurrent_roles_detected = len(intervals) > len(merged)

        provenance = ProvenanceRecord(
            field="years_experience",
            winning_value=years,
            winning_source="computed",
            winning_method="computed",
            winning_confidence=0.92,
            resolution_strategy="computed_from_date_ranges",
            all_claims=all_claims,
            conflict_detected=False,
            transformation_applied=[f"total_months:{total_months}", f"concurrent_roles:{concurrent_roles_detected}"]
        )
        return years, provenance

    def _strategy_union_skills(self, skill_claims: list[SkillClaim]) -> tuple[list[dict], ProvenanceRecord]:
        """Union with corroboration: pools unique skill names, adding corroboration bonuses for shared skills."""
        grouped = {}
        for c in skill_claims:
            if c.match_type == "unverified":
                key = c.raw_value.title().strip()
            else:
                key = c.canonical_name.strip()

            if not key:
                continue

            if key not in grouped:
                grouped[key] = []
            grouped[key].append(c)

        unique_skills = []
        for key, claims in grouped.items():
            sources = list(set(cl.source for cl in claims))
            max_conf = max(cl.confidence for cl in claims)

            # Apply corroboration bonus if skill was extracted from more than 1 source
            if len(sources) > 1:
                final_conf = min(1.0, max_conf + 0.15)
            else:
                final_conf = max_conf

            unique_skills.append({
                "name": key,
                "confidence": round(final_conf, 3),
                "sources": sources
            })

        # Sort descending by confidence score
        unique_skills.sort(key=lambda x: x["confidence"], reverse=True)

        winner_conf = unique_skills[0]["confidence"] if unique_skills else 0.0

        provenance = ProvenanceRecord(
            field="skills",
            winning_value=[dict(s) for s in unique_skills],
            winning_source="multiple",
            winning_method="union_with_corroboration",
            winning_confidence=winner_conf,
            resolution_strategy="union_with_corroboration",
            all_claims=[c.model_dump() for c in skill_claims],
            conflict_detected=False,
            transformation_applied=[]
        )
        return unique_skills, provenance

    def _strategy_merge_experience(self, exp_claims: list[Claim]) -> tuple[list[ExperienceEntry], ProvenanceRecord]:
        """Experience merger: groups roles by company and date range, merging properties into composite entries."""
        all_entries = []
        for claim in exp_claims:
            if isinstance(claim.raw_value, list):
                for entry in claim.raw_value:
                    all_entries.append(entry)

        if not all_entries:
            provenance = ProvenanceRecord(
                field="experience",
                winning_value=[],
                winning_source="none",
                winning_method="none",
                winning_confidence=0.0,
                resolution_strategy="merge_experience",
                all_claims=[c.model_dump() for c in exp_claims],
                conflict_detected=False,
                transformation_applied=[]
            )
            return [], provenance

        # Merge matching roles iteratively
        merged_list = []
        for entry in all_entries:
            merged = False
            for idx, existing in enumerate(merged_list):
                if self._is_same_role(entry, existing):
                    merged_list[idx] = self._merge_entries(existing, entry)
                    merged = True
                    break
            if not merged:
                # Copy entry to prevent reference mutations
                merged_list.append(entry.model_copy())

        # Update concurrency overlaps on final list
        intervals = []
        for idx, entry in enumerate(merged_list):
            s_val = self._date_to_int(entry.start)
            e_val = self._date_to_int(entry.end)
            intervals.append((s_val, e_val, idx))

        for i in range(len(intervals)):
            s1, e1, idx1 = intervals[i]
            for j in range(i + 1, len(intervals)):
                s2, e2, idx2 = intervals[j]
                if s1 <= e2 and s2 <= e1:
                    merged_list[idx1].concurrent = True
                    merged_list[idx2].concurrent = True

        # Sort jobs descending by start date (recent first)
        merged_list.sort(key=lambda x: self._date_to_int(x.start), reverse=True)

        winner_conf = max(e.confidence for e in merged_list) if merged_list else 0.0
        winner_source = ", ".join(list(set(src for e in merged_list for src in e.sources)))

        provenance = ProvenanceRecord(
            field="experience",
            winning_value=[e.model_dump() for e in merged_list],
            winning_source=winner_source,
            winning_method="merge_experience",
            winning_confidence=winner_conf,
            resolution_strategy="merge_experience",
            all_claims=[c.model_dump() for c in exp_claims],
            conflict_detected=False,
            transformation_applied=[f"merged_count:{len(merged_list)}"]
        )
        return merged_list, provenance

    def arbitrate(self, claims: list[Claim]) -> tuple[dict, list[ProvenanceRecord]]:
        """Processes claims list and runs field-by-field arbitration strategies, resolving canonical profile values."""
        # Clone all claims before performing mutations to preserve extraction state
        cloned_claims = [c.model_copy() for c in claims]

        # Step 1: Group claims by target field
        grouped_claims: dict[str, list[Claim]] = {}
        for c in cloned_claims:
            if c.field not in grouped_claims:
                grouped_claims[c.field] = []
            grouped_claims[c.field].append(c)

        # Step 2: Detect corroboration overlaps and increment confidence scores
        for field, claims_in_field in grouped_claims.items():
            for i in range(len(claims_in_field)):
                c1 = claims_in_field[i]
                for j in range(i + 1, len(claims_in_field)):
                    c2 = claims_in_field[j]
                    if self._are_claims_equal(c1, c2):
                        # Register corroborating source pathways
                        if c2.source not in c1.corroborated_by:
                            c1.corroborated_by.append(c2.source)
                        if c1.source not in c2.corroborated_by:
                            c2.corroborated_by.append(c1.source)
                        
                        # Add corroboration bonus (max 1.0)
                        c1.confidence = min(1.0, c1.confidence + 0.15)
                        c2.confidence = min(1.0, c2.confidence + 0.15)

        arbitrated_values: dict[str, Any] = {}
        provenance_records: list[ProvenanceRecord] = []

        # Step 3: Execute field-specific arbitration routines
        # Emails (Union)
        email_claims = grouped_claims.get("email", [])
        emails, email_prov = self._strategy_union(email_claims, "email")
        arbitrated_values["emails"] = emails
        provenance_records.append(email_prov)

        # Phones (Union)
        phone_claims = grouped_claims.get("phone", [])
        phones, phone_prov = self._strategy_union(phone_claims, "phone")
        arbitrated_values["phones"] = phones
        provenance_records.append(phone_prov)

        # Links (Union for each target link type)
        for link_field in ["linkedin_url", "github_url", "portfolio_url"]:
            link_claims = grouped_claims.get(link_field, [])
            vals, prov = self._strategy_union(link_claims, link_field)
            if link_field == "linkedin_url":
                arbitrated_values["linkedin_url"] = vals[0] if vals else None
            elif link_field == "github_url":
                arbitrated_values["github_url"] = vals[0] if vals else None
            elif link_field == "portfolio_url":
                # Portfolio can keep the whole list
                arbitrated_values["portfolio_url"] = vals
            provenance_records.append(prov)

        # Build combined links dictionary structure
        arbitrated_values["links"] = {
            "linkedin": arbitrated_values.get("linkedin_url"),
            "github": arbitrated_values.get("github_url"),
            "portfolio": arbitrated_values.get("portfolio_url") if isinstance(arbitrated_values.get("portfolio_url"), list) else ([arbitrated_values.get("portfolio_url")] if arbitrated_values.get("portfolio_url") else []),
            "other": []
        }
        # Clean up temporary url elements
        arbitrated_values.pop("linkedin_url", None)
        arbitrated_values.pop("github_url", None)
        arbitrated_values.pop("portfolio_url", None)

        # Full Name (Highest Confidence)
        name_claims = grouped_claims.get("full_name", [])
        name, name_prov = self._strategy_highest_confidence(name_claims, "full_name")
        arbitrated_values["full_name"] = name
        provenance_records.append(name_prov)

        # Headline (Highest Confidence)
        headline_claims = grouped_claims.get("headline", [])
        headline, headline_prov = self._strategy_highest_confidence(headline_claims, "headline")
        arbitrated_values["headline"] = headline
        provenance_records.append(headline_prov)

        # Location (Highest Confidence)
        loc_claims = grouped_claims.get("location", [])
        location, loc_prov = self._strategy_highest_confidence(loc_claims, "location")
        arbitrated_values["location"] = location if location else {"city": None, "region": None, "country": None}
        provenance_records.append(loc_prov)

        # Current Company (Highest Confidence)
        company_claims = grouped_claims.get("current_company", [])
        company, company_prov = self._strategy_highest_confidence(company_claims, "current_company")
        arbitrated_values["current_company"] = company
        provenance_records.append(company_prov)

        # Skills (Union Skills with Corroboration)
        skill_claims = [c for c in cloned_claims if c.field == "skills"]
        skills, skill_prov = self._strategy_union_skills(skill_claims)
        arbitrated_values["skills"] = skills
        provenance_records.append(skill_prov)

        # Experience (Role merging)
        exp_claims = grouped_claims.get("experience", [])
        experience, exp_prov = self._strategy_merge_experience(exp_claims)
        arbitrated_values["experience"] = experience
        provenance_records.append(exp_prov)

        # Education (Highest Confidence selection of overall lists)
        edu_claims = grouped_claims.get("education", [])
        education, edu_prov = self._strategy_highest_confidence(edu_claims, "education")
        arbitrated_values["education"] = education if education else []
        provenance_records.append(edu_prov)

        # Years Experience (Derive AFTER experience merger completes)
        # Collect all claims related to experience to attach to computed years provenance
        exp_claims_dicts = [c.model_dump() for c in exp_claims]
        years_exp, years_prov = self._strategy_computed_years_experience(experience, exp_claims_dicts)
        arbitrated_values["years_experience"] = years_exp
        provenance_records.append(years_prov)

        # Step 4: Compute overall confidence as a weighted score
        score_sum = 0.0
        weight_sum = 0.0

        for field, weight in FIELD_WEIGHTS.items():
            val = arbitrated_values.get(field)
            
            # Check populated status
            is_populated = False
            if val is not None:
                if isinstance(val, list):
                    is_populated = len(val) > 0
                elif isinstance(val, dict):
                    # Check if dict has non-null fields
                    is_populated = any(v is not None for v in val.values())
                elif isinstance(val, str):
                    is_populated = len(val.strip()) > 0
                else:
                    is_populated = True

            if is_populated:
                # Retrieve field confidence from resolved provenance record
                field_prov = next((p for p in provenance_records if p.field == field), None)
                conf = field_prov.winning_confidence if field_prov else 0.0
                
                score_sum += weight * 1.0 * conf
                weight_sum += weight

        overall_conf = (score_sum / weight_sum) if weight_sum > 0.0 else 0.0
        arbitrated_values["overall_confidence"] = round(overall_conf, 3)

        return arbitrated_values, provenance_records
