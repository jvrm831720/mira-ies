"""
Transformers para ERPs do mercado PME educacional brasileiro.

Mapeados conforme documento do MVP:
- JACAD, Sponte, SophiA (Prima), GVcollege (GVdasa), WPensar/Isaac
"""

from __future__ import annotations

from typing import Any

from app.services.connectors.base import (
    ConnectorInfo,
    pick,
    to_int,
    to_float,
    to_str,
)


def _as_list(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "alunos", "students", "items", "elements", "results", "records", "value"):
            if key in payload and isinstance(payload[key], list):
                return [x for x in payload[key] if isinstance(x, dict)]
        return [payload]
    return []


class JacadConnector:
    info = ConnectorInfo(
        id="jacad",
        name="JACAD",
        category="erp",
        description="Conector nativo de leitura REST; cadastro de alunos disponível, expansão acadêmica/financeira em homologação.",
        has_api=True,
        endpoints=["GET /api/v2/academico/alunos", "GET /api/v2/academico/matriculas", "GET /api/v2/financeiro/matriculas/resumo-financeiro", "GET /api/v1/financeiro/contratos-matricula/{idContrato}/parcelas"],
        docs_url="https://auden-developer.jacad.com.br/docs/academico",
        sample_fields=["idAluno", "ra", "nome", "statusMatricula", "situacaoFinanceira", "dataVencimentoParcela", "valorParcela"],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            matricula = to_str(pick(item, "ra", "codigoAluno", "codAluno", "matricula", "idAluno", "id"))
            nome = to_str(pick(item, "nome", "nomeAluno", "nomeCompleto"))
            if not matricula or not nome:
                continue
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "curso", "nomeCurso", "descricaoCurso")),
                "turma": to_str(pick(item, "turma", "codigoTurma", "classe")),
                "semestre": to_int(pick(item, "periodo", "semestre", "periodoAtual")),
                "forma_ingresso": to_str(pick(item, "formaIngresso", "tipoIngresso", "ingresso")),
                "telefone": to_str(pick(item, "telefone", "celular", "whatsapp", "fone", "telefoneAluno")),
                "email": to_str(pick(item, "email", "emailAluno", "emailInstitucional", "e_mail")),
                "dias_atraso_boleto": to_int(pick(item, "diasAtraso", "diasAtrasoBoleto", "atrasoFinanceiro")),
                "recorrencia_atrasos": to_int(pick(item, "qtdAtrasos", "recorrenciaAtrasos", "atrasosAnteriores")),
                "dias_sem_login": to_int(pick(item, "diasSemAcesso", "diasInativo", "ultimoAcessoDias")),
                "presenca_percentual": to_float(pick(item, "frequencia", "percentualPresenca", "presenca")),
                "nota_media": to_float(pick(item, "mediaGeral", "media", "notaMedia", "cr")),
                "reprovacoes": to_int(pick(item, "reprovacoes", "qtdReprovacoes")),
                "source_id": "jacad",
                "raw": item,
            })
        return records


class SponteConnector:
    info = ConnectorInfo(
        id="sponte",
        name="Sponte",
        category="erp",
        description="API oficial Sponte BI (alunos, contratos, financeiro, notas e frequência).",
        has_api=True,
        endpoints=[
                "GET /api/v1/extracoes/alunos", "GET /api/v1/extracoes/cursos",
                "GET /api/v1/extracoes/turmas", "GET /api/v1/extracoes/estagios",
                "GET /api/v1/extracoes/contratos", "GET /api/v1/extracoes/contratosturmasestagios",
                "GET /api/v1/extracoes/contasreceber", "GET /api/v1/extracoes/notas",
                "GET /api/v1/extracoes/fatofrequenciaalunosativos",
            ],
        sample_fields=["AlunoID", "Nome", "ContratoID", "contaReceberID", "notaDetalheID", "aulasAssistidas", "aulasTotais"],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            matricula = to_str(pick(item, "AlunoID", "CodigoAluno", "matricula", "RA", "IdAluno"))
            nome = to_str(pick(item, "Nome", "NomeAluno", "nome"))
            if not matricula or not nome:
                continue
            presenca = to_float(pick(item, "Frequencia", "PercentualPresenca", "Presenca"))
            if presenca is None:
                faltas = to_float(pick(item, "Faltas", "QtdFaltas"))
                total = to_float(pick(item, "TotalAulas", "AulasDadas"), 100)
                if faltas is not None and total:
                    presenca = max(0.0, 100.0 - (faltas / total * 100))
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "Curso", "NomeCurso")),
                "turma": to_str(pick(item, "Turma", "NomeTurma")),
                "semestre": to_int(pick(item, "Semestre", "Periodo", "Modulo")),
                "forma_ingresso": to_str(pick(item, "FormaIngresso", "Origem")),
                "telefone": to_str(pick(item, "Telefone", "Celular", "WhatsApp", "Fone", "TelefoneAluno")),
                "email": to_str(pick(item, "Email", "EmailAluno", "EmailInstitucional", "E-mail")),
                "dias_atraso_boleto": to_int(pick(item, "DiasAtraso", "DiasEmAtraso", "Atraso")),
                "recorrencia_atrasos": to_int(pick(item, "QtdAtrasos", "AtrasosAnteriores")),
                "dias_sem_login": to_int(pick(item, "DiasSemAcesso", "DiasInativo")),
                "presenca_percentual": presenca,
                "nota_media": to_float(pick(item, "Media", "MediaGeral", "Nota")),
                "reprovacoes": to_int(pick(item, "Reprovacoes", "QtdReprovacoes")),
                "saldo_devedor": to_float(pick(item, "SaldoDevedor", "saldo_devedor")),
                "status_financeiro": to_str(pick(item, "StatusFinanceiro", "status_financeiro")),
                "status_aluno": to_str(pick(item, "SituacaoAluno", "StatusAluno", "status_aluno")),
                "source_id": "sponte",
                "raw": item,
            })
        return records


class SophiaConnector:
    info = ConnectorInfo(
        id="sophia",
        name="SophiA (Prima)",
        category="erp",
        description="API Web Services REST (cadastro, notas, financeiro).",
        has_api=True,
        endpoints=["POST /api/v1/connectors/sophia/students", "POST /api/v1/connectors/sophia/sync"],
        sample_fields=["cod_aluno", "nome", "curso", "serie", "media", "frequencia", "vl_atraso"],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            matricula = to_str(pick(item, "cod_aluno", "codigo", "matricula", "ra", "id_aluno"))
            nome = to_str(pick(item, "nome", "nome_aluno", "nm_aluno"))
            if not matricula or not nome:
                continue
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "curso", "nm_curso", "descricao_curso")),
                "turma": to_str(pick(item, "turma", "serie", "classe")),
                "semestre": to_int(pick(item, "semestre", "periodo", "serie_num")),
                "forma_ingresso": to_str(pick(item, "forma_ingresso", "tp_ingresso")),
                "telefone": to_str(pick(item, "telefone", "celular", "fone", "telefone_aluno")),
                "email": to_str(pick(item, "email", "email_aluno", "e_mail", "nm_email")),
                "dias_atraso_boleto": to_int(pick(item, "dias_atraso", "vl_atraso_dias", "dias_atraso_boleto")),
                "recorrencia_atrasos": to_int(pick(item, "qtd_atrasos", "recorrencia")),
                "dias_sem_login": to_int(pick(item, "dias_sem_acesso", "dias_inativo")),
                "presenca_percentual": to_float(pick(item, "frequencia", "perc_frequencia", "presenca")),
                "nota_media": to_float(pick(item, "media", "media_geral", "nota")),
                "reprovacoes": to_int(pick(item, "reprovacoes", "qtd_reprov")),
                "source_id": "sophia",
                "raw": item,
            })
        return records


class GvcollegeConnector:
    info = ConnectorInfo(
        id="gvcollege",
        name="GVcollege (GVdasa)",
        category="erp",
        description="Web API (academico, financeiro, turmas).",
        has_api=True,
        endpoints=["POST /api/v1/connectors/gvcollege/students", "POST /api/v1/connectors/gvcollege/sync"],
        sample_fields=["alunoCodigo", "alunoNome", "cursoNome", "turmaCodigo", "financeiroDiasAtraso", "academicoMedia"],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            aluno = item.get("aluno") if isinstance(item.get("aluno"), dict) else item
            fin = item.get("financeiro") if isinstance(item.get("financeiro"), dict) else item
            acad = item.get("academico") if isinstance(item.get("academico"), dict) else item
            matricula = to_str(pick(aluno, "alunoCodigo", "codigo", "matricula", "ra", "id"))
            nome = to_str(pick(aluno, "alunoNome", "nome", "nomeCompleto"))
            if not matricula or not nome:
                continue
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "cursoNome", "curso") or pick(aluno, "curso")),
                "turma": to_str(pick(item, "turmaCodigo", "turma") or pick(aluno, "turma")),
                "semestre": to_int(pick(item, "periodo", "semestre") or pick(acad, "periodo")),
                "forma_ingresso": to_str(pick(aluno, "formaIngresso", "ingresso")),
                "telefone": to_str(
                    pick(aluno, "telefone", "celular", "whatsapp", "fone")
                    or pick(item, "telefone", "celular")
                ),
                "email": to_str(
                    pick(aluno, "email", "emailAluno", "e_mail")
                    or pick(item, "email", "emailAluno")
                ),
                "dias_atraso_boleto": to_int(pick(fin, "diasAtraso", "financeiroDiasAtraso", "diasAtrasoBoleto")),
                "recorrencia_atrasos": to_int(pick(fin, "qtdAtrasos", "recorrenciaAtrasos")),
                "dias_sem_login": to_int(pick(acad, "diasSemAcesso", "diasInativo")),
                "presenca_percentual": to_float(pick(acad, "frequencia", "academicoFrequencia", "presenca")),
                "nota_media": to_float(pick(acad, "media", "academicoMedia", "notaMedia")),
                "reprovacoes": to_int(pick(acad, "reprovacoes")),
                "source_id": "gvcollege",
                "raw": item,
            })
        return records


class WpensarConnector:
    info = ConnectorInfo(
        id="wpensar",
        name="WPensar / Isaac",
        category="erp",
        description="APIs de cobranca, conciliacao financeira e boletos (parcial).",
        has_api=True,
        endpoints=["POST /api/v1/connectors/wpensar/students", "POST /api/v1/connectors/wpensar/financial"],
        sample_fields=["student_id", "name", "days_overdue", "overdue_count", "product_name"],
    )

    def transform(self, payload: Any) -> list[dict[str, Any]]:
        records = []
        for item in _as_list(payload):
            matricula = to_str(pick(item, "student_id", "studentId", "matricula", "external_id", "id"))
            nome = to_str(pick(item, "name", "student_name", "nome", "full_name"))
            if not matricula or not nome:
                continue
            records.append({
                "matricula": matricula,
                "nome": nome,
                "curso": to_str(pick(item, "product_name", "course", "curso", "plan_name")),
                "turma": to_str(pick(item, "class_name", "turma")),
                "semestre": to_int(pick(item, "semester", "semestre")),
                "forma_ingresso": to_str(pick(item, "enrollment_type", "forma_ingresso")),
                "telefone": to_str(pick(item, "phone", "mobile_phone", "mobile", "whatsapp", "telefone")),
                "email": to_str(pick(item, "email", "email_address", "e_mail")),
                "dias_atraso_boleto": to_int(pick(item, "days_overdue", "dias_atraso", "overdue_days")),
                "recorrencia_atrasos": to_int(pick(item, "overdue_count", "qtd_atrasos", "previous_overdues")),
                "dias_sem_login": to_int(pick(item, "days_inactive", "dias_sem_login")),
                "presenca_percentual": to_float(pick(item, "attendance", "presenca")),
                "nota_media": to_float(pick(item, "grade_avg", "nota_media", "gpa")),
                "reprovacoes": to_int(pick(item, "failures", "reprovacoes")),
                "source_id": "wpensar",
                "raw": item,
            })
        return records
