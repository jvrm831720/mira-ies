"""Tenant-scoped dispatch outbox, leases, evidence and delivery events.

Revision ID: 055_dispatch_platform
Revises: 054_smart_import_custom_fields
"""
from alembic import op

revision = "055_dispatch_platform"
down_revision = "054_smart_import_custom_fields"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE dispatch_campaigns (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name VARCHAR(160) NOT NULL,
        purpose VARCHAR(30) NOT NULL CHECK (purpose IN ('retention','collections')),
        channel VARCHAR(20) NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
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
        CONSTRAINT dispatch_window_order CHECK (end_hour > start_hour)
    )
    """)
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
        external_event_id VARCHAR(180) NOT NULL,
        event_kind VARCHAR(30) NOT NULL,
        reply_intent VARCHAR(40),
        recommended_action VARCHAR(80),
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,provider,external_event_id),
        FOREIGN KEY (item_id,tenant_id) REFERENCES dispatch_items(id,tenant_id)
    )
    """)
    op.execute("""
    CREATE TABLE dispatch_payment_events (
        id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        obligation_ref VARCHAR(160) NOT NULL,
        source VARCHAR(80) NOT NULL,
        source_event_id VARCHAR(160) NOT NULL,
        amount_paid NUMERIC(14,2) NOT NULL CHECK (amount_paid >= 0),
        evidence_ref VARCHAR(200) NOT NULL,
        paid_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,source,source_event_id),
        FOREIGN KEY (tenant_id,obligation_ref)
            REFERENCES dispatch_obligations(tenant_id,external_ref)
    )
    """)
    op.execute("CREATE INDEX ix_dispatch_payments_obligation ON dispatch_payment_events(tenant_id,obligation_ref)")
    for table in (
        "dispatch_campaigns","dispatch_obligations","dispatch_external_contacts",
        "dispatch_items","dispatch_events","dispatch_rate_buckets","dispatch_inbound","dispatch_payment_events",
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
        "dispatch_payment_events","dispatch_inbound","dispatch_rate_buckets","dispatch_events","dispatch_items",
        "dispatch_external_contacts","dispatch_obligations","dispatch_campaigns",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
