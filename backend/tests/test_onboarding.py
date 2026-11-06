from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.core.security import hash_api_key
from app.models.auth import AuthChallenge, User
from app.models.organization import Membership, ModuleEntitlement, Organization, TenantBranding, TenantLogoAsset
from app.models.tenant import Tenant


def test_onboarding_helpers_validate_cnpj_and_slug():
    from app.api.onboarding import _slugify, _valid_cnpj

    assert _valid_cnpj("11.222.333/0001-81")
    assert not _valid_cnpj("00.000.000/0000-00")
    assert _slugify("Universidade São João") == "universidade-sao-joao"


def test_onboarding_enrichment_normalizes_public_inputs_and_registration_data():
    import pytest

    from app.services.onboarding_enrichment import normalize_company_data, normalize_public_website

    assert normalize_public_website("www.universidade.example.br") == "https://www.universidade.example.br"
    with pytest.raises(ValueError):
        normalize_public_website("http://127.0.0.1/admin")
    with pytest.raises(ValueError):
        normalize_public_website("http://localhost")

    company = normalize_company_data({
        "cnpj": "11.222.333/0001-81",
        "razao_social": " Universidade Exemplo  ",
        "nome_fantasia": "Exemplo",
        "descricao_situacao_cadastral": "ATIVA",
        "cnae_fiscal_descricao": "Educação superior",
        "logradouro": "Rua Um",
        "numero": "10",
        "municipio": "São Paulo",
        "uf": "SP",
        "unapproved_field": "must not leak",
    })
    assert company["legal_name"] == "Universidade Exemplo"
    assert company["trade_name"] == "Exemplo"
    assert "must not leak" not in str(company)


async def test_onboarding_enrichment_requires_live_verified_email_token(client):
    response = await client.post("/api/v1/onboarding/enrich", json={
        "onboarding_token": "invalid-onboarding-token-with-entropy",
        "email": "new.admin@university.test",
        "cnpj": "11222333000181",
        "website": "www.university.example.br",
    })
    assert response.status_code == 401


async def test_onboarding_enrichment_returns_reviewable_suggestions_without_writing(
    client, db_session, monkeypatch
):
    from app.api import onboarding

    email = "review.admin@university.test"
    token = "onboarding-enrichment-token-with-entropy"
    db_session.add(AuthChallenge(
        user_id=None,
        challenge_type="onboarding_provision",
        identifier_hash=hash_api_key(f"mira:challenge:onboarding:{email}"),
        token_hash=hash_api_key(f"mira:token:onboarding:{email}:{token}"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    ))
    await db_session.commit()

    async def fake_company(_cnpj):
        return {"cnpj": "11222333000181", "legal_name": "Universidade Exemplo"}

    async def fake_site(url, _api_key):
        return {"url": url, "title": "Universidade Exemplo", "markdown": "Conteúdo público"}

    monkeypatch.setattr(onboarding, "lookup_company", fake_company)
    monkeypatch.setattr(onboarding, "scrape_website", fake_site)
    monkeypatch.setattr(onboarding, "get_settings", lambda: SimpleNamespace(firecrawl_api_key="firecrawl-test-key"))

    response = await client.post("/api/v1/onboarding/enrich", json={
        "onboarding_token": token,
        "email": email,
        "cnpj": "11.222.333/0001-81",
        "website": "www.university.example.br",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["legal_name"] == "Universidade Exemplo"
    assert payload["website"]["title"] == "Universidade Exemplo"
    assert payload["warnings"] == []
    organization = (await db_session.execute(
        select(Organization).where(Organization.legal_name == "Universidade Exemplo")
    )).scalar_one_or_none()
    assert organization is None


async def test_verified_email_can_provision_organization_once(client, db_session):
    email = "primeiro.admin@universidade.test"
    onboarding_token = "onboarding-test-token-with-enough-entropy"
    now = datetime.now(timezone.utc)
    db_session.add(AuthChallenge(
        user_id=None,
        challenge_type="onboarding_provision",
        identifier_hash=hash_api_key(f"mira:challenge:onboarding:{email}"),
        token_hash=hash_api_key(f"mira:token:onboarding:{email}:{onboarding_token}"),
        expires_at=now + timedelta(minutes=30),
    ))
    await db_session.commit()

    payload = {
        "onboarding_token": onboarding_token,
        "email": email,
        "first_name": "Ana",
        "last_name": "Silva",
        "job_title": "Diretora de operações",
        "organization_name": "Universidade Horizonte",
        "trade_name": "Horizonte",
        "cnpj": "11222333000181",
        "website": "www.horizonte.edu.br",
        "institution_type": "university",
        "student_range": "5000_15000",
        "campuses": "2_5",
        "description": "Instituição de ensino superior com foco em permanência.",
        "data_sources": ["totvs_rm", "moodle"],
        "logo_data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9UKQsAAAAASUVORK5CYII=",
    }

    response = await client.post("/api/v1/onboarding/complete", json=payload)
    assert response.status_code == 201
    assert response.json()["mfa_enrollment_required"] is True
    assert response.json()["challenge_token"]

    organization = (await db_session.execute(
        select(Organization).where(Organization.legal_name == "Universidade Horizonte")
    )).scalar_one()
    tenant = (await db_session.execute(
        select(Tenant).where(Tenant.organization_id == organization.id)
    )).scalar_one()
    user = (await db_session.execute(
        select(User).where(User.email == email)
    )).scalar_one()
    membership = (await db_session.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.tenant_id == tenant.id,
        )
    )).scalar_one()
    entitlements = (await db_session.execute(
        select(ModuleEntitlement).where(ModuleEntitlement.tenant_id == tenant.id)
    )).scalars().all()

    assert user.role == "admin"
    assert membership.role == "admin"
    assert membership.origin == "self_service_onboarding"
    assert {item.module_key for item in entitlements} == {"permanence", "data", "workspace", "mira_plan"}
    assert organization.onboarding_profile["data_sources"] == ["totvs_rm", "moodle"]
    from sqlalchemy import text
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant.id},
    )
    logo = (await db_session.execute(
        select(TenantLogoAsset).where(TenantLogoAsset.tenant_id == tenant.id)
    )).scalar_one()
    branding = (await db_session.execute(
        select(TenantBranding).where(TenantBranding.tenant_id == tenant.id)
    )).scalar_one()
    assert logo.content_type == "image/png"
    assert logo.source == "uploaded"
    assert logo.image_bytes.startswith(b"\x89PNG")
    assert branding.logo_storage_key == f"database:tenant-logo/{tenant.id}"


    reused = await client.post("/api/v1/onboarding/complete", json=payload)
    assert reused.status_code == 401

def test_site_footer_cnpj_extraction_rejects_ambiguous_and_invalid_numbers():
    from app.services.onboarding_enrichment import extract_single_cnpj, site_favicon_url

    assert extract_single_cnpj("Rodapé: CNPJ: 11.222.333/0001-81") == "11222333000181"
    assert extract_single_cnpj("CNPJ inválido: 11.222.333/0001-82") is None
    assert extract_single_cnpj("11.222.333/0001-81 e 62.984.091/0001-02") is None
    assert site_favicon_url("https://example.com.br") == (
        "https://www.google.com/s2/favicons?domain=example.com.br&sz=128"
    )


def test_logo_payload_enforces_mime_and_size():
    import base64

    import pytest
    from fastapi import HTTPException
    from app.api.onboarding import _image_logo

    assert _image_logo("") is None
    with pytest.raises(HTTPException):
        _image_logo("data:image/png;base64," + base64.b64encode(b"not-a-png").decode())
    with pytest.raises(HTTPException):
        _image_logo("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")


async def test_logo_requires_authenticated_workspace(client):
    response = await client.get("/api/v1/onboarding/workspace-logo")
    assert response.status_code in {401, 403}
