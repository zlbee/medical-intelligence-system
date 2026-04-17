from __future__ import annotations

from typing import Any

from app.domain import (
    ArmGroupRef,
    InterventionRef,
    NormalizedTrialRecord,
    RawRecord,
    SourceName,
    SourceTrace,
)
from app.normalize.common import (
    clean_text,
    get_nested,
    normalize_enum_label,
    parse_partial_date,
    unique_strings,
)


class TrialNormalizer:
    """Maps ClinicalTrials.gov raw payloads into a stable trial domain object."""

    ACTIVE_STATUSES = {
        "NOT_YET_RECRUITING",
        "RECRUITING",
        "ENROLLING_BY_INVITATION",
        "ACTIVE_NOT_RECRUITING",
    }

    def normalize_many(self, records: list[RawRecord]) -> list[NormalizedTrialRecord]:
        normalized_by_key: dict[str, NormalizedTrialRecord] = {}
        for record in records:
            if record.source_name != SourceName.CLINICALTRIALS:
                continue

            normalized = self.normalize(record)
            existing = normalized_by_key.get(normalized.trial_key)
            if existing is None:
                normalized_by_key[normalized.trial_key] = normalized
                continue
            normalized_by_key[normalized.trial_key] = self._merge(existing, normalized)
        return list(normalized_by_key.values())

    def normalize(self, record: RawRecord) -> NormalizedTrialRecord:
        if record.source_name != SourceName.CLINICALTRIALS:
            raise ValueError("TrialNormalizer only accepts ClinicalTrials.gov records.")

        protocol = get_nested(record.payload, "protocolSection", default={}) or {}
        derived = get_nested(record.payload, "derivedSection", default={}) or {}

        identification = protocol.get("identificationModule", {}) or {}
        status = protocol.get("statusModule", {}) or {}
        description = protocol.get("descriptionModule", {}) or {}
        sponsors = protocol.get("sponsorCollaboratorsModule", {}) or {}
        conditions = protocol.get("conditionsModule", {}) or {}
        design = protocol.get("designModule", {}) or {}
        arms_interventions = protocol.get("armsInterventionsModule", {}) or {}
        contacts = protocol.get("contactsLocationsModule", {}) or {}
        outcomes = protocol.get("outcomesModule", {}) or {}
        condition_browse = derived.get("conditionBrowseModule", {}) or {}
        intervention_browse = derived.get("interventionBrowseModule", {}) or {}

        nct_id = clean_text(identification.get("nctId")) or clean_text(record.source_id)
        brief_summary = clean_text(description.get("briefSummary"))
        detailed_description = clean_text(description.get("detailedDescription"))
        summary = detailed_description or brief_summary
        phases = design.get("phases") or []

        normalized = NormalizedTrialRecord(
            trial_key=nct_id or record.record_id,
            nct_id=nct_id,
            source_traces=[self._build_source_trace(record)],
            brief_title=clean_text(identification.get("briefTitle")),
            official_title=clean_text(identification.get("officialTitle")),
            acronym=clean_text(identification.get("acronym")),
            summary=summary,
            study_type=normalize_enum_label(design.get("studyType")),
            phase=self._normalize_phase(phases),
            overall_status=normalize_enum_label(status.get("overallStatus")),
            last_known_status=normalize_enum_label(status.get("lastKnownStatus")),
            lead_sponsor=clean_text(get_nested(sponsors, "leadSponsor", "name")),
            collaborators=unique_strings(
                clean_text(item.get("name"))
                for item in sponsors.get("collaborators", []) or []
                if isinstance(item, dict)
            ),
            conditions=unique_strings(conditions.get("conditions", []) or []),
            keywords=unique_strings(conditions.get("keywords", []) or []),
            browse_terms=self._extract_browse_terms(condition_browse, intervention_browse),
            interventions=self._extract_interventions(arms_interventions),
            arm_groups=self._extract_arm_groups(arms_interventions),
            start_date=parse_partial_date(get_nested(status, "startDateStruct", "date")),
            primary_completion_date=parse_partial_date(
                get_nested(status, "primaryCompletionDateStruct", "date")
            ),
            completion_date=parse_partial_date(get_nested(status, "completionDateStruct", "date")),
            study_first_post_date=parse_partial_date(
                get_nested(status, "studyFirstPostDateStruct", "date")
            ),
            last_update_post_date=parse_partial_date(
                get_nested(status, "lastUpdatePostDateStruct", "date")
            ),
            enrollment=self._safe_int(get_nested(design, "enrollmentInfo", "count")),
            countries=self._extract_countries(contacts),
            location_count=self._count_locations(contacts),
            has_results=self._detect_results(record.payload),
            primary_outcomes=self._extract_outcomes(outcomes.get("primaryOutcomes", []) or []),
            secondary_outcomes=self._extract_outcomes(
                outcomes.get("secondaryOutcomes", []) or []
            ),
            quality_flags=self._build_quality_flags(
                phase=self._normalize_phase(phases),
                lead_sponsor=clean_text(get_nested(sponsors, "leadSponsor", "name")),
                conditions=conditions.get("conditions", []) or [],
                summary=summary,
            ),
        )
        return normalized

    def _merge(
        self,
        base: NormalizedTrialRecord,
        incoming: NormalizedTrialRecord,
    ) -> NormalizedTrialRecord:
        merged = base.model_copy(deep=True)
        merged.source_traces = [*base.source_traces, *incoming.source_traces]
        merged.collaborators = unique_strings([*base.collaborators, *incoming.collaborators])
        merged.conditions = unique_strings([*base.conditions, *incoming.conditions])
        merged.keywords = unique_strings([*base.keywords, *incoming.keywords])
        merged.browse_terms = unique_strings([*base.browse_terms, *incoming.browse_terms])
        merged.countries = unique_strings([*base.countries, *incoming.countries])
        merged.primary_outcomes = unique_strings(
            [*base.primary_outcomes, *incoming.primary_outcomes]
        )
        merged.secondary_outcomes = unique_strings(
            [*base.secondary_outcomes, *incoming.secondary_outcomes]
        )
        merged.quality_flags = unique_strings([*base.quality_flags, *incoming.quality_flags])
        merged.interventions = self._merge_named_models(base.interventions, incoming.interventions)
        merged.arm_groups = self._merge_named_models(base.arm_groups, incoming.arm_groups)

        for field_name in (
            "nct_id",
            "brief_title",
            "official_title",
            "acronym",
            "summary",
            "study_type",
            "phase",
            "overall_status",
            "last_known_status",
            "lead_sponsor",
            "start_date",
            "primary_completion_date",
            "completion_date",
            "study_first_post_date",
            "last_update_post_date",
            "enrollment",
            "location_count",
            "has_results",
        ):
            if getattr(merged, field_name) is None:
                setattr(merged, field_name, getattr(incoming, field_name))
        return merged

    def _build_source_trace(self, record: RawRecord) -> SourceTrace:
        return SourceTrace(
            raw_record_id=record.record_id,
            fetch_run_id=record.fetch_run_id,
            source_name=record.source_name,
            source_id=record.source_id,
            source_url=record.source_url,
            retrieved_at=record.retrieved_at,
        )

    def _normalize_phase(self, phases: list[str] | str | None) -> str | None:
        if phases is None:
            return None
        if isinstance(phases, str):
            normalized = normalize_enum_label(phases)
            return normalized
        normalized_phases = unique_strings(normalize_enum_label(item) for item in phases)
        if not normalized_phases:
            return None
        return "__".join(normalized_phases)

    def _extract_interventions(self, module: dict[str, Any]) -> list[InterventionRef]:
        interventions: list[InterventionRef] = []
        for item in module.get("interventions", []) or []:
            if not isinstance(item, dict):
                continue
            name = clean_text(item.get("name"))
            if name is None:
                continue
            interventions.append(
                InterventionRef(
                    name=name,
                    intervention_type=normalize_enum_label(item.get("type")),
                    other_names=unique_strings(item.get("otherNames", []) or []),
                )
            )
        return interventions

    def _extract_arm_groups(self, module: dict[str, Any]) -> list[ArmGroupRef]:
        arm_groups: list[ArmGroupRef] = []
        for item in module.get("armGroups", []) or []:
            if not isinstance(item, dict):
                continue
            label = clean_text(item.get("label"))
            if label is None:
                continue
            arm_groups.append(
                ArmGroupRef(
                    label=label,
                    arm_type=normalize_enum_label(item.get("type")),
                    description=clean_text(item.get("description")),
                    intervention_names=unique_strings(item.get("interventionNames", []) or []),
                )
            )
        return arm_groups

    def _extract_browse_terms(
        self,
        condition_browse: dict[str, Any],
        intervention_browse: dict[str, Any],
    ) -> list[str]:
        terms: list[str] = []
        for module in (condition_browse, intervention_browse):
            meshes = module.get("meshes", []) or []
            terms.extend(
                clean_text(item.get("term"))
                for item in meshes
                if isinstance(item, dict)
            )
        return unique_strings(terms)

    def _extract_countries(self, contacts_module: dict[str, Any]) -> list[str]:
        countries: list[str] = []
        for location in contacts_module.get("locations", []) or []:
            if not isinstance(location, dict):
                continue
            countries.append(clean_text(location.get("country")))
        return unique_strings(countries)

    def _count_locations(self, contacts_module: dict[str, Any]) -> int | None:
        locations = contacts_module.get("locations", []) or []
        if not locations:
            return None
        return len([item for item in locations if isinstance(item, dict)])

    def _extract_outcomes(self, outcomes: list[dict[str, Any]]) -> list[str]:
        return unique_strings(
            clean_text(item.get("measure"))
            for item in outcomes
            if isinstance(item, dict)
        )

    def _detect_results(self, payload: dict[str, Any]) -> bool | None:
        has_results = get_nested(payload, "hasResults")
        if isinstance(has_results, bool):
            return has_results
        results_section = payload.get("resultsSection")
        if results_section:
            return True
        return None

    def _build_quality_flags(
        self,
        *,
        phase: str | None,
        lead_sponsor: str | None,
        conditions: list[str],
        summary: str | None,
    ) -> list[str]:
        flags: list[str] = []
        if phase is None:
            flags.append("missing_phase")
        if lead_sponsor is None:
            flags.append("missing_lead_sponsor")
        if not conditions:
            flags.append("missing_conditions")
        if summary is None:
            flags.append("missing_summary")
        return flags

    def _safe_int(self, value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def _merge_named_models(self, base: list[Any], incoming: list[Any]) -> list[Any]:
        merged: dict[str, Any] = {}
        for item in [*base, *incoming]:
            key = getattr(item, "name", None) or getattr(item, "label", None)
            if key is None:
                continue
            merged[key.casefold()] = item
        return list(merged.values())
