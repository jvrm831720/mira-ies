"""Tenant-scoped dispatch outbox, leases, evidence and delivery events.

Revision ID: 055_dispatch_platform
Revises: 055_eligible_contrib_revocation
"""
from alembic import op

revision = "055_dispatch_platform"
down_revision = "055_eligible_contrib_revocation"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE dispatch_campaigns (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name VARCHAR(160) NOT NULL,
        purpose VARCHAR(30) NOT NULL CHECK (purpose IN ('retention','academic','service','collections')),
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
        delivery_mode VARCHAR(20) NOT NULL DEFAULT 'targeted' CHECK (delivery_mode IN ('individual','targeted','bulk')),
        source_kind VARCHAR(32) NOT NULL DEFAULT 'manual'
            CHECK (source_kind IN ('manual','native','composio','retention_proposal')),
        source_ref VARCHAR(160),
        source_tool_slug VARCHAR(120),
        origin_proposal_id UUID,
        origin_snapshot_hash VARCHAR(64),
        request_key VARCHAR(128),
        request_hash VARCHAR(64),
        template_ref VARCHAR(160) NOT NULL,
        template_body TEXT NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft','approved','scheduled','running','paused','completed','cancelled')),
        authorization_ref VARCHAR(200),
        created_by VARCHAR(80) NOT NULL,
        approved_by VARCHAR(80),
        approved_at TIMESTAMPTZ,
        scheduled_for TIMESTAMPTZ,
        timezone VARCHAR(80) NOT NULL DEFAULT 'America/Sao_Paulo',
        start_hour SMALLINT NOT NULL DEFAULT 9 CHECK (start_hour BETWEEN 8 AND 18),
        end_hour SMALLINT NOT NULL DEFAULT 18 CHECK (end_hour BETWEEN 9 AND 20),
        per_minute_limit INTEGER NOT NULL DEFAULT 10 CHECK (per_minute_limit BETWEEN 1 AND 120),
        daily_contact_limit INTEGER NOT NULL DEFAULT 1 CHECK (daily_contact_limit BETWEEN 1 AND 3),
        paused_reason VARCHAR(160),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (id, tenant_id),
        FOREIGN KEY (origin_proposal_id, tenant_id)
            REFERENCES retention_campaign_proposals(id, tenant_id),
        CONSTRAINT dispatch_origin_consistency CHECK (
            (source_kind='retention_proposal' AND origin_proposal_id IS NOT NULL
             AND source_ref = origin_proposal_id::text AND origin_snapshot_hash IS NOT NULL)
            OR (source_kind <> 'retention_proposal' AND origin_proposal_id IS NULL
                AND origin_snapshot_hash IS NULL)
        ),
        CONSTRAINT dispatch_source_shape CHECK (
            (source_kind='composio' AND source_ref IS NOT NULL AND source_tool_slug IS NOT NULL)
            OR (source_kind='native' AND source_ref IS NOT NULL AND source_tool_slug IS NULL)
            OR (source_kind='manual' AND source_tool_slug IS NULL)
            OR (source_kind='retention_proposal' AND source_tool_slug IS NULL)
        ),
        CONSTRAINT dispatch_window_order CHECK (end_hour > start_hour)
    )
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_dispatch_campaign_request
    ON dispatch_campaigns(tenant_id,request_key) WHERE request_key IS NOT NULL
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_dispatch_campaign_origin_proposal
    ON dispatch_campaigns(tenant_id,origin_proposal_id) WHERE origin_proposal_id IS NOT NULL
    """)
    op.execute("""
    CREATE TABLE dispatch_approved_templates (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        code VARCHAR(100) NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        purpose VARCHAR(30) NOT NULL CHECK (purpose IN ('retention','academic','service','collections')),
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
        subject VARCHAR(160) NOT NULL,
        body TEXT NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','retired')),
        created_by VARCHAR(80) NOT NULL,
        approved_by VARCHAR(80),
        approval_ref VARCHAR(200),
        approved_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,code,version)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_authorizations (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('student','external')),
        subject_ref VARCHAR(160) NOT NULL,
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
        purpose VARCHAR(30) NOT NULL CHECK (purpose IN ('retention','academic','service','collections')),
        evidence_ref VARCHAR(200) NOT NULL,
        source VARCHAR(80) NOT NULL,
        status VARCHAR(20) NOT NULL CHECK (status IN ('granted','revoked','expired')),
        verified_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,subject_type,subject_ref,channel,purpose)
    )
    """)
    op.execute("CREATE INDEX ix_dispatch_auth_expiry ON dispatch_authorizations(tenant_id,expires_at)")
    op.execute("""
    CREATE TABLE dispatch_provider_accounts (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        provider VARCHAR(40) NOT NULL CHECK (provider IN ('resend','twilio')),
        status VARCHAR(20) NOT NULL DEFAULT 'disabled' CHECK (status IN ('disabled','active')),
        credentials_ciphertext TEXT NOT NULL,
        credential_version INTEGER NOT NULL DEFAULT 1 CHECK (credential_version>=1),
        configured_by VARCHAR(80) NOT NULL,
        configured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_verified_at TIMESTAMPTZ,
        UNIQUE(tenant_id,provider)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_source_credentials (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        source VARCHAR(80) NOT NULL,
        scope VARCHAR(30) NOT NULL CHECK (
            scope IN ('authorization','financial','contacts','delivery')
        ),
        secret_ciphertext TEXT NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'disabled'
            CHECK (status IN ('disabled','active')),
        configured_by VARCHAR(80) NOT NULL,
        approved_by VARCHAR(80),
        approved_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (tenant_id,source,scope)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_source_nonces (
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        source VARCHAR(80) NOT NULL,
        scope VARCHAR(30) NOT NULL,
        nonce VARCHAR(80) NOT NULL,
        consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id,source,scope,nonce)
    )
    """)
    op.execute("CREATE INDEX ix_dispatch_nonce_retention ON dispatch_source_nonces(consumed_at)")
    op.execute("""
    CREATE TABLE dispatch_obligations (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        external_ref VARCHAR(160) NOT NULL,
        subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('student','external')),
        subject_ref VARCHAR(160) NOT NULL,
        status VARCHAR(20) NOT NULL CHECK (status IN ('open','paid','disputed','agreement','cancelled','unknown')),
        balance NUMERIC(14,2),
        source VARCHAR(80) NOT NULL,
        source_version BIGINT NOT NULL DEFAULT 0 CHECK (source_version>=0),
        evidence_ref VARCHAR(200) NOT NULL,
        verified_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id, external_ref)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_external_contacts (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        subject_ref VARCHAR(160) NOT NULL,
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms')),
        recipient_ciphertext TEXT NOT NULL,
        consent_ref VARCHAR(200) NOT NULL,
        opt_out BOOLEAN NOT NULL DEFAULT TRUE,
        verified_at TIMESTAMPTZ NOT NULL,
        UNIQUE(tenant_id, subject_ref, channel)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_items (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        campaign_id UUID NOT NULL,
        subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('student','external')),
        subject_ref VARCHAR(160) NOT NULL,
        obligation_ref VARCHAR(160),
        consent_ref VARCHAR(200) NOT NULL,
        channel VARCHAR(20) NOT NULL,
        status VARCHAR(24) NOT NULL DEFAULT 'queued'
            CHECK (status IN ('queued','leased','sending','retry_wait','simulated','sent','delivered','read','replied','failed','unknown','blocked','cancelled')),
        scheduled_for TIMESTAMPTZ NOT NULL DEFAULT now(),
        next_attempt_at TIMESTAMPTZ,
        attempt INTEGER NOT NULL DEFAULT 0,
        lease_owner VARCHAR(160),
        lease_token UUID,
        lease_until TIMESTAMPTZ,
        provider VARCHAR(40),
        provider_message_id VARCHAR(200),
        sent_at TIMESTAMPTZ,
        last_error VARCHAR(80),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(id, tenant_id),
        FOREIGN KEY (campaign_id, tenant_id) REFERENCES dispatch_campaigns(id, tenant_id) ON DELETE CASCADE
    )
    """)
    op.execute("""CREATE UNIQUE INDEX uq_dispatch_items_dedupe
        ON dispatch_items (tenant_id, campaign_id, subject_type, subject_ref, channel, coalesce(obligation_ref,''))""")
    op.execute("""CREATE INDEX ix_dispatch_items_due ON dispatch_items
        (status, scheduled_for, next_attempt_at) WHERE status IN ('queued','retry_wait')""")
    op.execute("""CREATE INDEX ix_dispatch_items_stale ON dispatch_items
        (lease_until) WHERE status IN ('leased','sending')""")
    op.execute("""CREATE INDEX ix_dispatch_items_recipient ON dispatch_items (tenant_id, subject_type, subject_ref, sent_at)""")
    op.execute("""
    CREATE TABLE dispatch_events (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        campaign_id UUID,
        item_id UUID,
        event_type VARCHAR(80) NOT NULL,
        event_key VARCHAR(200) NOT NULL,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (tenant_id,event_key),
        FOREIGN KEY (campaign_id, tenant_id) REFERENCES dispatch_campaigns(id, tenant_id),
        FOREIGN KEY (item_id, tenant_id) REFERENCES dispatch_items(id, tenant_id)
    )
    """)
    op.execute("CREATE INDEX ix_dispatch_events_campaign ON dispatch_events (tenant_id,campaign_id,occurred_at)")
    op.execute("""
    CREATE TABLE dispatch_rate_buckets (
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        bucket_key VARCHAR(160) NOT NULL,
        tokens NUMERIC(12,3) NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(tenant_id, bucket_key)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_inbound (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        item_id UUID,
        provider VARCHAR(40) NOT NULL,
        provider_message_id VARCHAR(200) NOT NULL,
        external_event_id VARCHAR(180) NOT NULL,
        event_hash VARCHAR(64) NOT NULL,
        event_kind VARCHAR(30) NOT NULL,
        reply_intent VARCHAR(40),
        recommended_action VARCHAR(80),
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,provider,external_event_id),
        FOREIGN KEY (item_id,tenant_id) REFERENCES dispatch_items(id,tenant_id)
    )
    """)
    op.execute("""
    CREATE INDEX ix_dispatch_inbound_pending
    ON dispatch_inbound(tenant_id,provider,provider_message_id)
    WHERE item_id IS NULL
    """)
    op.execute("""
    CREATE TABLE dispatch_payment_events (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        obligation_ref VARCHAR(160) NOT NULL,
        source VARCHAR(80) NOT NULL,
        source_event_id VARCHAR(160) NOT NULL,
        source_version BIGINT NOT NULL CHECK (source_version>=1),
        amount_paid NUMERIC(14,2) NOT NULL CHECK (amount_paid >= 0),
        obligation_status VARCHAR(20) NOT NULL,
        remaining_balance NUMERIC(14,2) NOT NULL,
        evidence_ref VARCHAR(200) NOT NULL,
        paid_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,source,source_event_id),
        FOREIGN KEY (tenant_id,obligation_ref)
            REFERENCES dispatch_obligations(tenant_id,external_ref)
    )
    """)
    op.execute("CREATE INDEX ix_dispatch_payments_obligation ON dispatch_payment_events(tenant_id,obligation_ref)")
    op.execute("""
    CREATE TABLE dispatch_suppressions (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        subject_type VARCHAR(20) NOT NULL CHECK (subject_type IN ('student','external')),
        subject_ref VARCHAR(160) NOT NULL,
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('all','email','sms','whatsapp')),
        reason VARCHAR(80) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,subject_type,subject_ref,channel)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_worker_heartbeats (
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        worker_id VARCHAR(160) NOT NULL,
        seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        stats JSONB NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY(tenant_id,worker_id)
    )
    """)
    for table in (
        "dispatch_campaigns","dispatch_approved_templates","dispatch_authorizations","dispatch_provider_accounts","dispatch_source_credentials","dispatch_source_nonces","dispatch_obligations","dispatch_external_contacts",
        "dispatch_items","dispatch_events","dispatch_rate_buckets","dispatch_inbound","dispatch_payment_events","dispatch_worker_heartbeats","dispatch_suppressions",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """)
    op.execute("""
    CREATE FUNCTION dispatch_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'dispatch_events is append-only';
    END;
    $$;
    """)
    op.execute("""
    CREATE TRIGGER dispatch_payments_immutable BEFORE UPDATE OR DELETE
    ON dispatch_payment_events FOR EACH ROW EXECUTE FUNCTION dispatch_events_append_only()
    """)
    op.execute("""
    CREATE TRIGGER dispatch_events_immutable BEFORE UPDATE OR DELETE
    ON dispatch_events FOR EACH ROW EXECUTE FUNCTION dispatch_events_append_only()
    """)

def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS dispatch_events_immutable ON dispatch_events")
    op.execute("DROP TRIGGER IF EXISTS dispatch_payments_immutable ON dispatch_payment_events")
    op.execute("DROP FUNCTION IF EXISTS dispatch_events_append_only()")
    for table in (
        "dispatch_suppressions","dispatch_worker_heartbeats","dispatch_payment_events","dispatch_inbound","dispatch_rate_buckets","dispatch_events","dispatch_items",
        "dispatch_external_contacts","dispatch_obligations","dispatch_source_nonces","dispatch_source_credentials","dispatch_provider_accounts","dispatch_authorizations","dispatch_approved_templates","dispatch_campaigns",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
