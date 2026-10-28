"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS).

Módulo de entrada legível: o router completo vive em agents_routes e agents_analytics.
"""

from app.api.agents_routes import router  # noqa: F401

# Register analytics / dead-letter routes on the shared router.
from app.api import agents_analytics  # noqa: F401, E402
