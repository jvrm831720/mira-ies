"""Materialize an approved MIRA retention proposal as ONE dispatch execution.

The proposal remains the campaign-governance source of truth. The dispatch
record is its unique execution/outbox, not a second independently approved
retention campaign. Individual channel authorization is still mandatory.
"""
from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.retention_campaign import RetentionCampaignProposal
from app.services.campaign_proposals import hash_audience_snapshot
from app.services.dispatch_core import audit, bind_tenant


async def materialize_proposal(
    db: AsyncSession, *, tenant_id: str, actor: str,
    proposal_id: str, template_id: str,
) -> dict:
    if not actor or not proposal_id or not template_id:
        raise ValueError("Solicitante, proposta e modelo aprovado são obrigatórios.")
    try:
        proposal_id = str(UUID(proposal_id))
        template_id = str(UUID(template_id))
    except (ValueError, TypeError) as exc:
        raise ValueError("Identificador de proposta ou modelo inválido.") from exc
    await bind_tenant(db, tenant_id)
    proposal = (await db.execute(
        select(RetentionCampaignProposal).where(
            RetentionCampaignProposal.tenant_id == tenant_id,
            RetentionCampaignProposal.id == proposal_id,
        ).with_for_update()
    )).scalar_one_or_none()
    if proposal is None:
        raise LookupError("Proposta não encontrada neste workspace.")
    if (
        proposal.status != "approved"
        or proposal.created_by is None
        or proposal.approved_by is None or proposal.approved_at is None
        or proposal.created_by == proposal.approved_by
        or proposal.authorization_status != "institution_attested"
        or proposal.authorization_attested_by is None
        or proposal.authorization_attested_by == proposal.created_by
        or not proposal.authorization_reference
        or len(proposal.authorization_reference) < 8
    ):
        raise ValueError("Proposta de permanência não possui governança e autorização aprovadas.")

    snapshot = proposal.audience_snapshot or []
    if hash_audience_snapshot(snapshot) != proposal.audience_hash:
        raise ValueError("Snapshot da proposta foi alterado após revisão.")

    template = (await db.execute(text("""
        SELECT id, subject, body, channel, purpose FROM dispatch_approved_templates
        WHERE tenant_id=:tenant AND id=:template AND status='approved'
    """), {"tenant": tenant_id, "template": template_id})).mappings().first()
    if template is None or template["purpose"] != "retention":
        raise ValueError("Escolha modelo de permanência já aprovado pelo workspace.")
    if template["channel"] not in (proposal.recommended_channels or []):
        raise ValueError("O canal do modelo não está recomendado na proposta aprovada.")

    fingerprint = hashlib.sha256(
        f"{tenant_id}:{proposal.id}:{proposal.audience_hash}:{template_id}".encode()
    ).hexdigest()
    claim_key = hashlib.sha256(
        f"retention-proposal:{tenant_id}:{proposal.id}".encode()
    ).hexdigest()
    previous = (await db.execute(text("""
        SELECT id,request_hash,status FROM dispatch_campaigns
        WHERE tenant_id=:tenant AND origin_proposal_id=:proposal
    """), {"tenant": tenant_id, "proposal": str(proposal.id)})).mappings().first()
    if previous:
        if previous["request_hash"] != fingerprint:
            raise ValueError("Já existe uma execução vinculada a esta proposta com outro modelo.")
        return {
            "id": str(previous["id"]), "status": previous["status"],
            "origin_proposal_id": str(proposal.id), "deduplicated": True,
        }

    candidates = [
        row for row in snapshot
        if isinstance(row, dict)
        and template["channel"] in row.get("eligible_channels", [])
        and not row.get("blocked_reasons")
        and not row.get("internal_action_only")
        and row.get("student_id")
    ]
    if not candidates or len(candidates) > 1000:
        raise ValueError("Proposta exige de 1 a 1.000 destinatários elegíveis neste canal.")

    ids = [str(row["student_id"]) for row in candidates]
    trusted_sources = [
        value.strip()
        for value in get_settings().dispatch_trusted_authorization_sources.split(",")
        if value.strip()
    ]
    if not trusted_sources:
        raise ValueError("Nenhuma fonte de autorização individual foi configurada.")
    authorizations = (await db.execute(text("""
        SELECT subject_ref, evidence_ref FROM dispatch_authorizations
        WHERE tenant_id=:tenant AND subject_type='student'
          AND channel=:channel AND purpose='retention'
          AND status='granted' AND expires_at > now()
          AND verified_at >= now() - interval '90 days'
          AND source=ANY(CAST(:sources AS text[]))
          AND subject_ref=ANY(CAST(:ids AS text[]))
    """), {
        "tenant": tenant_id, "channel": template["channel"],
        "sources": trusted_sources, "ids": ids,
    })).mappings().all()
    allowed = {row["subject_ref"]: row["evidence_ref"] for row in authorizations}
    student_rows = (await db.execute(text("""
        SELECT id::text AS id, communication_opt_out, communication_preferences,
               is_active FROM students
        WHERE tenant_id=:tenant AND id::text=ANY(CAST(:ids AS text[]))
    """), {"tenant": tenant_id, "ids": ids})).mappings().all()
    current = {row["id"]: row for row in student_rows}
    selected: list[tuple[str, str]] = []
    for row in candidates:
        student_id = str(row["student_id"])
        student = current.get(student_id)
        consent_ref = allowed.get(student_id)
        if not student or not student["is_active"] or student["communication_opt_out"] or not consent_ref:
            continue
        prefs = student["communication_preferences"] or {}
        if (
            prefs.get("channels", {}).get(template["channel"]) is not True
            or prefs.get("topics", {}).get("retention") is not True
        ):
            continue
        selected.append((student_id, consent_ref))
    selected = list(dict(selected).items()) if selected else []
    if not selected:
        raise ValueError("Nenhum destinatário permanece autorizado para contato.")

    campaign_id = str(uuid4())
    created = (await db.execute(text("""
        INSERT INTO dispatch_campaigns (
            id,tenant_id,name,purpose,channel,delivery_mode,
            source_kind,source_ref,origin_proposal_id,origin_snapshot_hash,
            request_key,request_hash,template_ref,template_body,status,
            authorization_ref,created_by,approved_by,approved_at,timezone
        ) VALUES (
            :id,:tenant,:name,'retention',:channel,'targeted',
            'retention_proposal',:proposal,:proposal,:snapshot,
            :key,:hash,:subject,:body,'approved',
            :authorization,:actor,:approver,:approved_at,:timezone
        )
        ON CONFLICT (tenant_id,origin_proposal_id)
          WHERE origin_proposal_id IS NOT NULL DO NOTHING
        RETURNING id
    """), {
        "id": campaign_id, "tenant": tenant_id, "name": proposal.title,
        "channel": template["channel"], "proposal": str(proposal.id),
        "snapshot": proposal.audience_hash, "key": claim_key, "hash": fingerprint,
        "subject": template["subject"], "body": template["body"],
        "authorization": proposal.authorization_reference,
        "actor": actor, "approver": proposal.approved_by,
        "approved_at": proposal.approved_at,
        "timezone": proposal.schedule_timezone or "America/Sao_Paulo",
    })).scalar_one_or_none()
    if created is None:
        prior = (await db.execute(text("""
            SELECT id,status,request_hash FROM dispatch_campaigns
            WHERE tenant_id=:tenant AND origin_proposal_id=:proposal
        """), {"tenant": tenant_id, "proposal": str(proposal.id)})).mappings().one()
        if prior["request_hash"] != fingerprint:
            raise ValueError("A proposta já está vinculada a uma execução diferente.")
        await db.commit()
        return {"id": str(prior["id"]), "status": prior["status"],
                "origin_proposal_id": str(proposal.id), "deduplicated": True}
    for student_id, consent_ref in selected:
        await db.execute(text("""
            INSERT INTO dispatch_items (
                id,tenant_id,campaign_id,subject_type,subject_ref,consent_ref,channel
            ) VALUES (
                :id,:tenant,:campaign,'student',:subject,:consent,:channel
            ) ON CONFLICT DO NOTHING
        """), {
            "id": str(uuid4()), "tenant": tenant_id, "campaign": campaign_id,
            "subject": student_id, "consent": consent_ref,
            "channel": template["channel"],
        })
    await audit(
        db, tenant_id=tenant_id, campaign_id=campaign_id,
        event_type="campaign.retention_proposal_materialized",
        details={
            "actor": actor, "proposal_id": str(proposal.id),
            "approved_by": proposal.approved_by,
            "selected_count": len(selected), "snapshot_hash": proposal.audience_hash,
        },
    )
    await db.commit()
    return {
        "id": campaign_id, "status": "approved",
        "origin_proposal_id": str(proposal.id),
        "selected_count": len(selected), "deduplicated": False,
    }
