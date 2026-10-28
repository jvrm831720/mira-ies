"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS).

Corpo completo recuperado da versão saudável pré-truncamento (histório pré-4342004),
com hardening de list_retention_logs. Não é um módulo mínimo: expande o fonte integral.
"""
from __future__ import annotations

import base64
import zlib
from pathlib import Path

_dir = Path(__file__).resolve().parent
_BODY = (_dir / "_agents_body_a.b64").read_text(encoding="utf-8").strip() + (
    _dir / "_agents_body_b.b64"
).read_text(encoding="utf-8").strip()
_SRC = zlib.decompress(base64.b64decode(_BODY)).decode("utf-8")
exec(compile(_SRC, str(_dir / "_agents_expanded.py"), "exec"), globals())
