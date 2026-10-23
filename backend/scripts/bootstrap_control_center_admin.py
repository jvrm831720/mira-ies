"""Bootstrap único do primeiro Super Admin do Control Center.

Uso: defina ADMIN_EMAIL, ADMIN_NAME, ADMIN_PASSWORD e
ADMIN_BOOTSTRAP_CONFIRM=CREATE_FIRST_ADMIN no ambiente, então execute:
python -m scripts.bootstrap_control_center_admin

Não passe a senha em argumentos de linha de comando nem registre-a em logs.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

from sqlalchemy import func, select

from app.core.mira_security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.control_center import AdminAuditEvent, AdminPrincipal


async def main() -> int:
    if os.getenv("ADMIN_BOOTSTRAP_CONFIRM") != "CREATE_FIRST_ADMIN":
        print("Defina ADMIN_BOOTSTRAP_CONFIRM=CREATE_FIRST_ADMIN para confirmar o bootstrap.")
        return 2

    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    name = os.getenv("ADMIN_NAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        print("ADMIN_EMAIL inválido.")
        return 2
    if not name or len(name) > 120 or len(password) < 14 or len(password) > 256:
        print("Informe ADMIN_NAME válido e ADMIN_PASSWORD com 14 a 256 caracteres.")
        return 2

    async with AsyncSessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(AdminPrincipal))
        if count:
            print("Bootstrap bloqueado: já existe uma identidade interna. Use um processo administrativo revisado.")
            return 3
        admin = AdminPrincipal(
            email=email, display_name=name, password_hash=hash_password(password),
            role="super_admin", is_active=True,
        )
        db.add(admin)
        await db.flush()
        db.add(AdminAuditEvent(
            actor_admin_id=admin.id, action="admin_bootstrap_created",
            result="success", target_type="AdminPrincipal", target_id=admin.id,
            reason="Bootstrap inicial via ambiente operacional protegido",
        ))
        await db.commit()
        print(f"Super Admin inicial criado para {email}. Configure MFA por e-mail antes de iniciar uma sessão.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
