"""Rotas do sistema multiagente de retencao (orquestrador + canais WhatsApp/E-mail/SMS).

Pacote legível em Python convencional (sem exec/zlib):
  agents_common, agents_run, agents_ops, agents_logs, agents_analytics, agents_deadletter.
"""

from app.api.agents_common import router  # noqa: F401

from app.api import agents_run  # noqa: F401, E402
from app.api import agents_ops  # noqa: F401, E402
from app.api import agents_logs  # noqa: F401, E402
from app.api import agents_analytics  # noqa: F401, E402
from app.api import agents_deadletter  # noqa: F401, E402
