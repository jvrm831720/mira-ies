"""Alembic environment — usa DATABASE_URL_SYNC do settings."""
from __future__ import annotations
import sys
from pathlib import Path
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import Base
import app.models.student  # noqa: F401
import app.models.native_academic  # noqa: F401
import app.models.academic_catalog  # noqa: F401
import app.models.academic_operations  # noqa: F401
import app.models.student_services  # noqa: F401
import app.models.financial_composio  # noqa: F401
import app.models.finance_reconciliation  # noqa: F401
import app.models.student_payments  # noqa: F401
import app.models.asaas_live  # noqa: F401
import app.models.student_document_attestation  # noqa: F401
import app.models.tenant  # noqa: F401
import app.models.educational_outcome  # noqa: F401
import app.models.intervention  # noqa: F401
import app.models.consent  # noqa: F401
import app.models.engagement  # noqa: F401
import app.models.retention_campaign  # noqa: F401
import app.models.control_center  # noqa: F401
import app.models.data_governance  # noqa: F401
import app.models.institutional_training_authorization  # noqa: F401
import app.models.work_activity  # noqa: F401
import app.models.auth  # noqa: F401
import app.models.jacad_connection  # noqa: F401
import app.models.sponte_connection  # noqa: F401
import app.models.rm_sync  # noqa: F401
import app.models.rm_sync_jobs  # noqa: F401
import app.models.connector_destination  # noqa: F401
import app.models.composio_connection  # noqa: F401
import app.models.composio_approval  # noqa: F401
import app.models.integration_features  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url_sync.replace("%", "%%"),
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
