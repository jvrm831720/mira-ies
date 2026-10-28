"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS)."""

from app.api._agents_routes import router  # noqa: F401

# Side-effect imports register additional routes on the shared router.
from app.api import _agents_analytics  # noqa: F401, E402
