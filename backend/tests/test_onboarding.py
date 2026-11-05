from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_api_key
from app.models.auth import AuthChallenge, User
from app.models.organization import Membership, ModuleEntitlement, Organization
from app.models.tenant import Tenant


def test_onboarding_helpers_validate_cnpj_and_slug():
    from app.api.onboarding import _slugify, _valid_cnpj

    assert _valid_cnpj("11.222.333/0001-81")
    assert not _valid_cnpj("00.000.000/0000-00")
    assert _slugify("Universidade São João") == "universidade-sao-joao"


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

    reused = await client.post("/api/v1/onboarding/complete", json=payload)
    assert reused.status_code == 401
