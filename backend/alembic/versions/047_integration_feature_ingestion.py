"""Feature ingestion contract: data-source policies and student observations.

Revision ID: 047_integration_feature_ingestion
Revises: 046_composio_toolkit_policies
"""
from alembic import op

revision = "047_integration_feature_ingestion"
down_revision = "046_composio_toolkit_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tenant_integration_data_sources (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_kind VARCHAR(32) NOT NULL
                CHECK (source_kind IN ('native_connector', 'composio', 'upload', 'system')),
            source_key VARCHAR(80) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            feature_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by_user_id UUID NULL REFERENCES mira_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_integration_data_source
                UNIQUE (tenant_id, source_kind, source_key),
            CONSTRAINT ck_integration_data_source_key
                CHECK (source_key ~ '^[a-z0-9][a-z0-9_.-]{0,79}$'),
            CONSTRAINT ck_integration_feature_keys_array
                CHECK (jsonb_typeof(feature_keys) = 'array')
        )
    """)
    op.execute("""
        CREATE INDEX ix_tenant_integration_data_sources_enabled
        ON tenant_integration_data_sources (tenant_id, is_enabled)
    """)
    op.execute("ALTER TABLE tenant_integration_data_sources ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_integration_data_sources FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_integration_data_sources_isolation
        ON tenant_integration_data_sources
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)

    op.execute("""
        CREATE TABLE student_feature_observations (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            student_id UUID NULL REFERENCES students(id) ON DELETE CASCADE,
            subject_ref VARCHAR(160) NULL,
            observation_key VARCHAR(200) NOT NULL,
            source_kind VARCHAR(32) NOT NULL
                CHECK (source_kind IN ('native_connector', 'composio', 'upload', 'system')),
            source_key VARCHAR(80) NOT NULL,
            feature_key VARCHAR(64) NOT NULL,
            value_type VARCHAR(16) NOT NULL
                CHECK (value_type IN ('number', 'text', 'boolean', 'categorical')),
            value_number DOUBLE PRECISION NULL,
            value_text VARCHAR(500) NULL,
            value_boolean BOOLEAN NULL,
            reliability VARCHAR(20) NOT NULL DEFAULT 'partial',
            observed_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_student_feature_observation_key
                UNIQUE (tenant_id, observation_key),
            CONSTRAINT ck_feature_observation_feature_key
                CHECK (feature_key ~ '^[a-z][a-z0-9_]{1,63}$')
        )
    """)
    op.execute("""
        CREATE INDEX ix_feature_obs_tenant_student_feature
        ON student_feature_observations (tenant_id, student_id, feature_key)
    """)
    op.execute("""
        CREATE INDEX ix_feature_obs_tenant_source_time
        ON student_feature_observations (tenant_id, source_kind, source_key, observed_at)
    """)
    op.execute("""
        CREATE INDEX ix_feature_obs_tenant_feature_time
        ON student_feature_observations (tenant_id, feature_key, observed_at)
    """)
    op.execute("ALTER TABLE student_feature_observations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE student_feature_observations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY student_feature_observations_isolation
        ON student_feature_observations
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS student_feature_observations")
    op.execute("DROP TABLE IF EXISTS tenant_integration_data_sources")
