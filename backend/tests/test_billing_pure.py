"""Testes puros do catálogo de créditos e isolamento do _STORE (sem Postgres)."""
from __future__ import annotations

import importlib


def _billing():
    return importlib.import_module("app.api.billing")


def test_credit_packs_catalog_is_authoritative():
    m = _billing()
    assert set(m.CREDIT_PACKS.keys()) == {"starter", "growth", "scale"}
    assert m.CREDIT_PACKS["starter"]["credits"] == 500
    assert m.CREDIT_PACKS["growth"]["credits"] == 2000
    assert m.CREDIT_PACKS["scale"]["credits"] == 8000
    for pack in m.CREDIT_PACKS.values():
        assert pack["credits"] > 0
        assert pack["price_brl"] >= 0


def test_store_is_keyed_by_tenant_id():
    m = _billing()
    m._STORE.clear()
    a = m._state_for("tenant-a")
    b = m._state_for("tenant-b")
    assert a is not b
    a["credits"]["whatsapp"] = 1
    b["credits"]["whatsapp"] = 999
    assert m._state_for("tenant-a")["credits"]["whatsapp"] == 1
    assert m._state_for("tenant-b")["credits"]["whatsapp"] == 999
    m._STORE.clear()


def test_purchase_body_rejects_unknown_pack_logic():
    m = _billing()
    pack = m.CREDIT_PACKS.get("does-not-exist")
    assert pack is None


def test_purchase_credits_mismatch_detection():
    m = _billing()
    pack = m.CREDIT_PACKS["growth"]
    client_credits = 9999
    assert client_credits != int(pack["credits"])


def test_default_state_is_synthetic_not_ledger():
    """Documenta que defaults são MVP sintéticos — não cobrança real."""
    m = _billing()
    state = m._default_state()
    assert "plan_name" in state
    assert "invoices" in state
    assert isinstance(state["invoices"], list)
    # payment_link ausente = sem gateway configurado
    assert state.get("payment_link") is None
