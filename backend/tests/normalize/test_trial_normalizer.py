from __future__ import annotations

from datetime import datetime, timezone

from app.domain import RawRecord, SourceName
from app.normalize import TrialNormalizer


def test_trial_normalizer_maps_core_clinicaltrials_fields() -> None:
    normalizer = TrialNormalizer()
    record = RawRecord(
        fetch_run_id="fetch-1",
        source_name=SourceName.CLINICALTRIALS,
        source_id="NCT00000001",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        target="HER2",
        indication="breast cancer",
        payload={
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT00000001",
                    "briefTitle": "HER2 trial",
                    "officialTitle": "A Phase II HER2 Trial",
                    "acronym": "H2T",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                    "startDateStruct": {"date": "2025-01-15"},
                    "studyFirstPostDateStruct": {"date": "2024-12-01"},
                },
                "descriptionModule": {
                    "briefSummary": "Short summary",
                    "detailedDescription": "Detailed summary",
                },
                "sponsorCollaboratorsModule": {
                    "leadSponsor": {"name": "Example Sponsor"},
                    "collaborators": [{"name": "Partner Org"}],
                },
                "conditionsModule": {
                    "conditions": ["Breast Cancer"],
                    "keywords": ["HER2", "ERBB2"],
                },
                "designModule": {
                    "studyType": "INTERVENTIONAL",
                    "phases": ["PHASE2"],
                    "enrollmentInfo": {"count": 42},
                },
                "armsInterventionsModule": {
                    "interventions": [
                        {
                            "type": "DRUG",
                            "name": "Example Drug",
                            "otherNames": ["Drug Alias"],
                        }
                    ],
                    "armGroups": [
                        {
                            "label": "Arm A",
                            "type": "EXPERIMENTAL",
                            "description": "Main arm",
                            "interventionNames": ["Example Drug"],
                        }
                    ],
                },
                "contactsLocationsModule": {
                    "locations": [
                        {"country": "United States"},
                        {"country": "China"},
                    ]
                },
                "outcomesModule": {
                    "primaryOutcomes": [{"measure": "ORR"}],
                    "secondaryOutcomes": [{"measure": "PFS"}],
                },
            },
            "derivedSection": {
                "conditionBrowseModule": {"meshes": [{"term": "Breast Neoplasms"}]},
                "interventionBrowseModule": {"meshes": [{"term": "ERBB2 Proteins"}]},
            },
            "resultsSection": {"dummy": True},
        },
        query_snapshot={"source": "clinicaltrials"},
        retrieved_at=datetime.now(timezone.utc),
    )

    normalized = normalizer.normalize(record)

    assert normalized.trial_key == "NCT00000001"
    assert normalized.phase == "PHASE2"
    assert normalized.overall_status == "RECRUITING"
    assert normalized.lead_sponsor == "Example Sponsor"
    assert normalized.conditions == ["Breast Cancer"]
    assert normalized.interventions[0].name == "Example Drug"
    assert normalized.arm_groups[0].label == "Arm A"
    assert normalized.countries == ["United States", "China"]
    assert normalized.has_results is True
    assert normalized.primary_outcomes == ["ORR"]
    assert "Breast Neoplasms" in normalized.browse_terms
