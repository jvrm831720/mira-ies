"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS).

Pacote legível: agents_routes (run/enqueue/jobs/send-time/work-summary),
agents_logs (logs/outcome/preview/status), agents_analytics (analytics/dead-letter).
"""

from app.api.agents_routes import router  # noqa: F401

# Side-effect imports register remaining routes on the shared router.
from app.api import agents_logs  # noqa: F401, E402
from app.api import agents_analytics  # noqa: F401, E402
