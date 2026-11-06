from datetime import datetime, timezone

from app.services.connectors.provenance import build_provenance_coverage


def test_coverage_counts_only_explicit_valid_observed_at():
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    rows = [
        {
            "_mira_provenance": {
                "dias_sem_login": {
                    "observed_at": "2026-11-01T12:00:00Z",
                    "imported_at": "2026-11-02T00:00:00Z",
                },
                "nota_media": {
                    "source_updated_at": "2026-11-01T12:00:00Z",
                },
            }
        },
        {
            "_mira_provenance": {
                "dias_sem_login": {"observed_at": "not-a-date"},
                "nota_media": {"observed_at": "2026-11-03T00:00:00Z"},
            }
        },
    ]

    result = build_provenance_coverage(rows, now=now)

    assert result["records_total"] == 2
    assert result["fields"]["dias_sem_login"]["observed_at_valid"] == 1
    assert result["fields"]["dias_sem_login"]["invalid_or_future"] == 1
    assert result["fields"]["nota_media"]["observed_at_valid"] == 0
    assert result["fields"]["nota_media"]["missing"] == 1
    assert result["fields"]["nota_media"]["invalid_or_future"] == 1
    assert result["observations_with_valid_timestamp"] == 1


def test_empty_tenant_coverage_is_zero_without_division_errors():
    result = build_provenance_coverage([])

    assert result["records_total"] == 0
    assert result["coverage_pct"] == 0.0
    assert all(item["coverage_pct"] == 0.0 for item in result["fields"].values())


def test_imported_at_does_not_count_as_observation_timestamp():
    result = build_provenance_coverage([
        {"_mira_provenance": {
            "dias_sem_login": {"imported_at": "2026-11-02T00:00:00Z"}
        }}
    ])

    assert result["fields"]["dias_sem_login"]["observed_at_valid"] == 0
    assert result["fields"]["dias_sem_login"]["missing"] == 1
