"""Semantic normalization for Sponte BI extraction records."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any


def pick(row: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).casefold().replace("_", ""): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.casefold().replace("_", ""))
        if value not in (None, ""):
            return value
    return None


def as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(".", "").replace(",", ".") if "," in value else value.strip()
        return float(value)
    except (TypeError, ValueError):
        return None


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt, length in (
        ("%Y-%m-%d", 10), ("%d/%m/%Y", 10),
        ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S.%f", 26),
    ):
        try:
            return datetime.strptime(text[:length], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def is_excluded(row: dict[str, Any]) -> bool:
    value = pick(row, "Excluido", "Excluida", "Deleted")
    return str(value).strip().casefold() in {"1", "true", "sim", "s", "yes"}


def aluno_id(row: dict[str, Any]) -> str | None:
    value = pick(row, "AlunoID", "CodigoAluno", "IdAluno", "AlunoId")
    return str(value).strip() if value is not None else None


def record_id(endpoint: str, row: dict[str, Any]) -> str:
    fields = {
        "alunos": ("AlunoID", "CodigoAluno", "IdAluno"),
        "contratos": ("ContratoID", "IdContrato"),
        "contratosturmasestagios": ("ContratoTurmaID", "ContratoID", "TurmaID", "EstagioID"),
        "cursos": ("CursoID", "IdCurso"),
        "turmas": ("TurmaID", "IdTurma"),
        "estagios": ("EstagioID", "IdEstagio"),
        "contasreceber": ("contaReceberID", "ContaReceberID", "IdContaReceber"),
        "notas": ("notaDetalheID", "NotaDetalheID", "IdNotaDetalhe"),
        "fatofrequenciaalunosativos": ("FatoFrequenciaAlunoAtivoID", "AlunoID", "ContratoID", "DataExtracao"),
        "fatoalunosativos": ("FatoAlunoAtivoID", "AlunoID", "ContratoID", "DataExtracao"),
        "followups": ("FollowUpID", "IdFollowUp", "FollowupID"),
    }.get(endpoint, ())
    values = [str(pick(row, field)) for field in fields if pick(row, field) is not None]
    if values:
        return ":".join(values)
    encoded = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def compact_row(endpoint: str, row: dict[str, Any]) -> dict[str, Any]:
    common = {
        "aluno_id": aluno_id(row),
        "contrato_id": pick(row, "ContratoID", "IdContrato"),
        "data_extracao": pick(row, "DataExtracao"),
        "excluido": is_excluded(row),
    }
    if endpoint == "alunos":
        return {
            **common,
            "nome": pick(row, "Nome", "NomeAluno"),
            "situacao_aluno": pick(row, "SituacaoAluno", "StatusAluno"),
            "email": pick(row, "Email", "EmailAluno"),
            "telefone": pick(row, "FoneCelular", "FoneResidencial", "Telefone", "Celular", "TelefoneAluno"),
            "data_cadastro": pick(row, "DataCadastro"),
            "numero_matricula": pick(row, "NumeroMatricula"),
            "funcionario_id": pick(row, "FuncionarioID"),
            "responsavel_id": pick(row, "ResponsavelID", "ResponsavelId"),
        }
    if endpoint in {"contratos", "contratosturmasestagios", "fatoalunosativos"}:
        return {
            **common,
            "curso_id": pick(row, "CursoID", "IdCurso"),
            "curso": pick(row, "NomeCurso", "Curso"),
            "turma_id": pick(row, "TurmaID", "IdTurma"),
            "turma": pick(row, "NomeTurma", "Turma"),
            "estagio_id": pick(row, "EstagioID", "IdEstagio"),
            "estagio": pick(row, "NomeEstagio", "Estagio"),
            "situacao": pick(row, "SituacaoAluno", "SituacaoContrato", "SituacaoEstagio", "Situacao", "Status"),
            "data_contrato": pick(row, "DataContrato"),
            "data_inicio": pick(row, "DataInicio"),
            "data_matricula": pick(row, "DataMatricula"),
            "inicio_atividades": pick(row, "InicioAtividades"),
            "data_fim": pick(row, "DataFim"),
            "contrato_aula_livre": pick(row, "ContratoAulaLivre"),
            "semestre": pick(row, "Semestre", "Periodo"),
            "ano": pick(row, "Ano"),
        }
    if endpoint == "contasreceber":
        return {
            **common,
            "conta_receber_id": pick(row, "contaReceberID", "ContaReceberID", "IdContaReceber"),
            "numero_parcela": pick(row, "NumeroParcela", "Parcela"),
            "numero_total_parcelas": pick(row, "NumeroTotalParcelas", "TotalParcelas"),
            "situacao": pick(row, "Situacao", "Status"),
            "data_vencimento": pick(row, "DataVencimentoParcela", "DataVencimento"),
            "data_pagamento": pick(row, "DataPagamentoParcela", "DataPagamento"),
            "valor_total": pick(row, "ValorTotalParcela", "ValorParcela"),
            "valor_pago": pick(row, "ValorPagoParcela", "ValorPago"),
            "tipo_recebimento": pick(row, "TipoRecebimentoParcela", "TipoRecebimento"),
            "situacao_id": pick(row, "SituacaoID"),
            "valor_desconto": pick(row, "ValorDescontoParcela"),
            "valor_total_desconto": pick(row, "ValorTotalDescontoParcela"),
        }
    if endpoint == "notas":
        return {
            **common,
            "nota_detalhe_id": pick(row, "notaDetalheID", "NotaDetalheID", "IdNotaDetalhe"),
            "curso_id": pick(row, "CursoID", "IdCurso"),
            "curso": pick(row, "NomeCurso", "Curso"),
            "turma_id": pick(row, "TurmaID", "IdTurma"),
            "turma": pick(row, "NomeTurma", "Turma"),
            "estagio": pick(row, "Estagio", "NomeEstagio"),
            "avaliacao": pick(row, "Avaliacao", "NomeAvaliacao"),
            "nota": pick(row, "Nota", "ValorNota"),
            "media": pick(row, "Media", "MediaFinal"),
            "conceito": pick(row, "Conceito"),
            "conceito_media": pick(row, "ConceitoMedia"),
            "prova": pick(row, "Prova"),
            "aulas_repostas": pick(row, "AulasRepostas"),
            "sistema_avaliacao": pick(row, "SistemaAvaliacao"),
            "data": pick(row, "Data"),
            "situacao_didatica": pick(row, "SituacaoDidatica"),
            "semestre": pick(row, "Semestre", "Periodo"),
            "ano": pick(row, "Ano"),
        }
    if endpoint == "cursos":
        return {
            "curso_id": pick(row, "CursoID", "IdCurso"),
            "nome": pick(row, "Nome", "Curso", "NomeCurso"),
            "sigla": pick(row, "Sigla"),
            "ativo": pick(row, "Ativo"),
            "excluido": is_excluded(row),
        }
    if endpoint == "turmas":
        return {
            "turma_id": pick(row, "TurmaID", "IdTurma"),
            "nome": pick(row, "Nome", "Turma", "NomeTurma"),
            "curso_id": pick(row, "CursoID", "IdCurso"),
            "estagio_id": pick(row, "EstagioID", "IdEstagio"),
            "semestre": pick(row, "Semestre"),
            "ano": pick(row, "Ano"),
            "data_inicio": pick(row, "DataInicio"),
            "data_termino": pick(row, "DataTermino"),
            "situacao": pick(row, "SituacaoTurma"),
            "excluido": is_excluded(row),
        }
    if endpoint == "estagios":
        return {
            "estagio_id": pick(row, "EstagioID", "IdEstagio"),
            "nome": pick(row, "Nome", "Estagio", "NomeEstagio"),
            "curso_id": pick(row, "CursoID", "IdCurso"),
            "idioma": pick(row, "Idioma"),
            "excluido": is_excluded(row),
        }
    if endpoint == "fatofrequenciaalunosativos":
        return {
            **common,
            "aulas_dadas": pick(row, "AulasDadas"),
            "aulas_assistidas": pick(row, "AulasAssistidas"),
            "aulas_totais": pick(row, "AulasTotais"),
            "total_faltas": pick(row, "TotalFaltas"),
        }
    if endpoint == "followups":
        return {
            **common,
            "followup_id": pick(row, "FollowUpID", "IdFollowUp", "FollowupID"),
            "data_followup": pick(row, "DataFollowUp", "Data"),
            "tipo": pick(row, "TipoContato", "Tipo", "TipoFollowUp"),
            "canal": pick(row, "Canal"),
            "resultado": pick(row, "ResultadoVisita", "Resultado", "Status"),
            "atendente_id": pick(row, "AtendenteID"),
            "motivo_nao_fechamento_id": pick(row, "MotivoNaoFechamentoID"),
        }
    return common


def build_student_payloads(
    students: list[dict[str, Any]], *, as_of: date, catalogs: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    catalogs = catalogs or {}
    for student in students:
        raw = student.raw_data or {}
        sponte = raw.get("sponte") or {}
        profile = sponte.get("profile") or {}
        aluno = student.matricula
        if profile.get("excluido"):
            enriched.append({
                "AlunoID": aluno,
                "Nome": profile.get("nome") or student.nome,
                "Curso": None,
                "Turma": None,
                "Semestre": None,
                "Email": profile.get("email") or student.email,
                "Telefone": profile.get("telefone") or student.telefone,
                "DiasAtraso": None,
                "QtdAtrasos": None,
                "SaldoDevedor": None,
                "StatusFinanceiro": None,
                "SituacaoAluno": "EXCLUIDO",
                "Frequencia": None,
                "raw_sponte": sponte,
                "finance_observed_at": None,
                "attendance_observed_at": None,
            })
            continue
        contracts = [
            row for row in (sponte.get("contratos") or {}).values()
            if not row.get("excluido") and row.get("aluno_id") == aluno
        ]
        class_links = [
            row for row in (sponte.get("contratosturmasestagios") or {}).values()
            if not row.get("excluido") and row.get("aluno_id") == aluno
        ]
        if class_links:
            contracts.extend(class_links)
        contracts.sort(key=lambda row: as_date(
            row.get("data_contrato") or row.get("data_inicio") or row.get("data_matricula") or row.get("inicio_atividades")
        ) or date.min)
        current_contract = contracts[-1] if contracts else {}
        course = catalogs.get("cursos", {}).get(str(current_contract.get("curso_id")), {})
        turma = catalogs.get("turmas", {}).get(str(current_contract.get("turma_id")), {})
        estagio = catalogs.get("estagios", {}).get(str(current_contract.get("estagio_id")), {})
        if course.get("excluido"):
            course = {}
        if turma.get("excluido"):
            turma = {}
        if estagio.get("excluido"):
            estagio = {}

        fact_students = [
            row for row in (sponte.get("fatoalunosativos") or {}).values()
            if not row.get("excluido") and row.get("aluno_id") == aluno
        ]
        fact_students.sort(key=lambda row: as_date(row.get("data_extracao")) or date.min)
        latest_fact_date = as_date(fact_students[-1].get("data_extracao")) if fact_students else None
        latest_facts = [
            row for row in fact_students
            if latest_fact_date and as_date(row.get("data_extracao")) == latest_fact_date
        ]
        active_contract_ids = {
            str(row.get("contrato_id")) for row in latest_facts
            if row.get("contrato_id") is not None
        }
        active_contracts = [
            row for row in contracts
            if row.get("contrato_id") is not None
            and str(row.get("contrato_id")) in active_contract_ids
        ]
        active_contracts.sort(key=lambda row: as_date(
            row.get("data_contrato") or row.get("data_inicio") or row.get("data_matricula") or row.get("inicio_atividades")
        ) or date.min)
        current_contract = active_contracts[-1] if active_contracts else {}
        course = catalogs.get("cursos", {}).get(str(current_contract.get("curso_id")), {})
        turma = catalogs.get("turmas", {}).get(str(current_contract.get("turma_id")), {})
        estagio = catalogs.get("estagios", {}).get(str(current_contract.get("estagio_id")), {})
        if course.get("excluido"):
            course = {}
        if turma.get("excluido"):
            turma = {}
        if estagio.get("excluido"):
            estagio = {}

        # Financial facts are scoped to contracts present in the latest active-contract snapshot.
        # Without that snapshot, historical receivables are not safe to classify as current debt.
        receivables = [
            row for row in (sponte.get("contasreceber") or {}).values()
            if (
                active_contract_ids
                and not row.get("excluido")
                and row.get("aluno_id") == aluno
                and row.get("contrato_id") is not None
                and str(row.get("contrato_id")) in active_contract_ids
            )
        ]
        paid_statuses = {"pago", "paga", "quitado", "quitada"}
        pending = [row for row in receivables if str(row.get("situacao") or "").strip().casefold() == "pendente"]
        unknown_status = any(
            str(row.get("situacao") or "").strip().casefold() not in (paid_statuses | {"pendente"})
            for row in receivables
        )
        overdue = []
        due_date_unknown = False
        balance = 0.0
        balance_complete = bool(active_contract_ids) and not unknown_status
        for row in pending:
            due = as_date(row.get("data_vencimento"))
            if due is None:
                due_date_unknown = True
            elif due < as_of:
                overdue.append((as_of - due).days)
            total = as_number(row.get("valor_total"))
            paid = as_number(row.get("valor_pago"))
            if total is None or paid is None:
                balance_complete = False
            else:
                balance += max(0.0, total - paid)
        if overdue:
            financial_status = "VENCIDO"
        elif pending and (due_date_unknown or unknown_status):
            financial_status = None
        elif pending:
            financial_status = "EM_ABERTO"
        elif active_contract_ids and not receivables:
            financial_status = "SEM_FINANCEIRO"
        elif receivables and all(str(row.get("situacao") or "").strip().casefold() in paid_statuses for row in receivables):
            financial_status = "PAGO"
        else:
            financial_status = None

        attendance = [
            row for row in (sponte.get("fatofrequenciaalunosativos") or {}).values()
            if (
                active_contract_ids
                and not row.get("excluido")
                and row.get("aluno_id") == aluno
                and row.get("contrato_id") is not None
                and str(row.get("contrato_id")) in active_contract_ids
            )
        ]
        latest_attendance_by_contract: dict[str, dict[str, Any]] = {}
        for row in attendance:
            contract_id = str(row.get("contrato_id"))
            previous = latest_attendance_by_contract.get(contract_id)
            row_date = as_date(row.get("data_extracao")) or date.min
            previous_date = as_date(previous.get("data_extracao")) or date.min if previous else date.min
            if previous is None or row_date > previous_date:
                latest_attendance_by_contract[contract_id] = row
        latest_attendance_rows = list(latest_attendance_by_contract.values())
        attendance_values = [
            (as_number(row.get("aulas_assistidas")), as_number(row.get("aulas_totais")))
            for row in latest_attendance_rows
        ]
        attendance_complete = (
            bool(active_contract_ids)
            and set(latest_attendance_by_contract) == active_contract_ids
            and bool(attendance_values)
            and all(
                attended is not None and total is not None
                and total > 0 and 0 <= attended <= total
                for attended, total in attendance_values
            )
        )
        attended_total = sum(attended for attended, _ in attendance_values if attended is not None)
        classes_total = sum(total for _, total in attendance_values if total is not None)
        presence = attended_total / classes_total * 100 if attendance_complete and classes_total > 0 else None
        latest_attendance = max(
            latest_attendance_rows,
            key=lambda row: as_date(row.get("data_extracao")) or date.min,
            default={},
        )

        notes = [
            row for row in (sponte.get("notas") or {}).values()
            if not row.get("excluido") and row.get("aluno_id") == aluno
        ]
        notes.sort(key=lambda row: (int(as_number(row.get("ano")) or 0), int(as_number(row.get("semestre")) or 0)))
        latest_note = notes[-1] if notes else {}
        latest_fact = latest_facts[-1] if latest_facts else {}

        enriched.append({
            "AlunoID": aluno,
            "Nome": profile.get("nome") or student.nome,
            "Curso": current_contract.get("curso") or course.get("nome") or latest_note.get("curso") or student.curso,
            "Turma": current_contract.get("turma") or turma.get("nome") or latest_note.get("turma") or student.turma,
            "Semestre": latest_note.get("semestre") or current_contract.get("semestre") or turma.get("semestre"),
            "Email": profile.get("email") or student.email,
            "Telefone": profile.get("telefone") or student.telefone,
            "DiasAtraso": None if (not active_contract_ids or due_date_unknown or unknown_status) else (max(overdue) if overdue else 0),
            # Current overdue installments are not historical delinquency recurrence.
            "QtdAtrasos": None,
            "SaldoDevedor": balance if balance_complete else None,
            "StatusFinanceiro": financial_status,
            "SituacaoAluno": profile.get("situacao_aluno") or latest_fact.get("situacao"),
            "Frequencia": presence,
            "raw_sponte": sponte,
            "finance_observed_at": None,
            "attendance_observed_at": latest_attendance.get("data_extracao"),
        })
    return enriched
