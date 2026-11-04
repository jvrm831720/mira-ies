from app.services.connectors.gvcollege_ingestion import (
    build_gvcollege_ingestion_preview,
    dry_run_gvcollege_ingestion,
    ingestion_preview_to_dict,
)


TENANT = "tenant-synthetic-wave3"
INGESTED_AT = "2026-11-03T12:00:00+00:00"


def test_dry_run_normalizes_synthetic_row_and_preserves_unknowns():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{
            "matricula": "SYN-0001",
            "nome": "Aluno Sintético 001",
            "curso": "Curso de Teste",
            "semestre": None,
            "dias_sem_login": 8,
        }],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_accepted == 1
    assert report.persisted is False
    assert report.scoring_executed is False
    assert report.remote_requests == 0
    assert report.records[0].data["semestre"] is None
    assert report.records[0].data["presenca_percentual"] is None
    assert report.records[0].tenant_id == TENANT
    assert len(report.records[0].idempotency_key) == 64


def test_dry_run_rejects_unknown_fields_and_tenant_injection():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{
            "matricula": "SYN-0002",
            "nome": "Aluno Sintético 002",
            "tenant_id": "another-tenant",
            "campo_novo": "unexpected",
        }],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_accepted == 0
    assert report.rows_rejected == 1
    assert {issue.code for issue in report.issues} == {
        "tenant_scope_injection", "unknown_source_fields"
    }


def test_dry_run_rejects_invalid_types_and_missing_required_fields():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{"matricula": "SYN-0003", "nome": None, "semestre": "três"}],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_rejected == 1
    assert "required_field_missing" in {issue.code for issue in report.issues}
    assert "invalid_field_type" in {issue.code for issue in report.issues}


def test_dry_run_rejects_duplicate_pagination_keys():
    rows = [
        {"matricula": "SYN-0004", "nome": "Aluno Sintético 004"},
        {"matricula": "SYN-0004", "nome": "Aluno Sintético 004 duplicado"},
    ]
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1", rows, tenant_id=TENANT, ingested_at=INGESTED_AT
    )
    assert report.rows_accepted == 1
    assert report.rows_rejected == 1
    assert report.issues[0].code == "duplicate_source_record_id"


def test_dry_run_is_deterministic_for_idempotency_key():
    row = [{"matricula": "SYN-0005", "nome": "Aluno Sintético 005"}]
    first = dry_run_gvcollege_ingestion(
        "synthetic_students_v1", row, tenant_id=TENANT, ingested_at=INGESTED_AT
    )
    second = dry_run_gvcollege_ingestion(
        "synthetic_students_v1", row, tenant_id=TENANT, ingested_at=INGESTED_AT
    )
    assert first.records[0].idempotency_key == second.records[0].idempotency_key


def test_dry_run_rejects_naive_observation_timestamp():
    try:
        dry_run_gvcollege_ingestion(
            "synthetic_students_v1",
            [{"matricula": "SYN-0006", "nome": "Aluno Sintético 006"}],
            tenant_id=TENANT,
            observed_at="2026-11-03T12:00:00",
            ingested_at=INGESTED_AT,
        )
    except ValueError as exc:
        assert "fuso horário" in str(exc)
    else:
        raise AssertionError("Timestamp sem fuso deveria ser rejeitado")


def test_dry_run_rejects_empty_ingested_at():
    try:
        dry_run_gvcollege_ingestion(
            "synthetic_students_v1",
            [{"matricula": "SYN-0007", "nome": "Aluno Sintético 007"}],
            tenant_id=TENANT,
            ingested_at="",
        )
    except ValueError as exc:
        assert "não vazia" in str(exc)
    else:
        raise AssertionError("Timestamp vazio deveria ser rejeitado")


def test_preview_summarizes_results_without_exposing_student_values():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [
            {"matricula": "SYN-0008", "nome": "Nome Sintético Privado"},
            {"matricula": "SYN-0009", "nome": None},
        ],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    preview = ingestion_preview_to_dict(build_gvcollege_ingestion_preview(report))
    serialized = str(preview)
    assert preview["rows_received"] == 2
    assert preview["rows_accepted"] == 1
    assert preview["rows_rejected"] == 1
    assert preview["issue_counts"] == {"required_field_missing": 1}
    assert "Nome Sintético Privado" not in serialized
    assert "SYN-0008" not in serialized
    assert preview["persisted"] is False
    assert preview["scoring_executed"] is False
    assert preview["remote_requests"] == 0


def test_preview_limits_issue_details_and_reports_truncation():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{"matricula": f"SYN-{index:04}", "nome": None} for index in range(1, 4)],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    preview = build_gvcollege_ingestion_preview(report, max_issue_details=1)
    assert preview.issues_total == 3
    assert len(preview.issues) == 1
    assert preview.issues_truncated is True


def test_dry_run_rejects_blank_required_string():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{"matricula": "SYN-0010", "nome": "   "}],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_rejected == 1
    assert "required_field_blank" in {issue.code for issue in report.issues}


def test_rejected_row_does_not_reserve_duplicate_source_id():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [
            {"matricula": "SYN-0011", "nome": None},
            {"matricula": "SYN-0011", "nome": "Aluno Sintético 011"},
        ],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_accepted == 1
    assert report.rows_rejected == 1
    assert report.records[0].source_record_id == "SYN-0011"
    assert "duplicate_source_record_id" not in {issue.code for issue in report.issues}


def test_dry_run_rejects_integer_outside_signed_64_bit_range():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{"matricula": "SYN-0012", "nome": "Aluno Sintético 012", "semestre": 2**80}],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_rejected == 1
    assert "invalid_field_type" in {issue.code for issue in report.issues}


def test_dry_run_rejects_non_string_source_field_names_without_crashing():
    report = dry_run_gvcollege_ingestion(
        "synthetic_students_v1",
        [{1: "unexpected", "matricula": "SYN-0013", "nome": "Aluno Sintético 013"}],
        tenant_id=TENANT,
        ingested_at=INGESTED_AT,
    )
    assert report.rows_rejected == 1
    assert "invalid_source_field_name" in {issue.code for issue in report.issues}
