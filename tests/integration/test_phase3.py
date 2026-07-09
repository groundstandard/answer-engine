"""Phase 3: domain policy packs, cost routing, RBAC."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.config.settings import settings
from backend.config.policy_loader import resolve_profile_for_domain, load_policy_config
from backend.orchestration.pipeline import PipelineController
from backend.orchestration.model_client import MODEL_OVERRIDES


# ---- C: domain policy packs ----

def test_legal_and_financial_profiles_exist():
    assert resolve_profile_for_domain("legal") == "legal"
    assert resolve_profile_for_domain("financial") == "financial"
    assert load_policy_config("legal").minimum_claim_support_ratio == 0.96
    assert load_policy_config("financial").minimum_freshness_score == 0.85


# ---- D: cost routing ----

class _Cls:
    def __init__(self, risk):
        self.risk_level = risk
        self.classification_label = "LOW_RISK_FACTUAL"


def test_cost_routing_low_risk_uses_cheaper_model(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_COST_ROUTING", True)
    pc = PipelineController.__new__(PipelineController)
    tok = MODEL_OVERRIDES.set({})
    try:
        pc._apply_cost_routing(_Cls(0.1))
        assert MODEL_OVERRIDES.get()["DRAFT"] == settings.llm_fallback_model
    finally:
        MODEL_OVERRIDES.reset(tok)


def test_cost_routing_high_risk_untouched(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_COST_ROUTING", True)
    pc = PipelineController.__new__(PipelineController)
    tok = MODEL_OVERRIDES.set({})
    try:
        pc._apply_cost_routing(_Cls(0.9))
        assert MODEL_OVERRIDES.get() == {}
    finally:
        MODEL_OVERRIDES.reset(tok)


def test_cost_routing_respects_tenant_override(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_COST_ROUTING", True)
    pc = PipelineController.__new__(PipelineController)
    tok = MODEL_OVERRIDES.set({"DRAFT": "tenant-model"})
    try:
        pc._apply_cost_routing(_Cls(0.1))
        assert MODEL_OVERRIDES.get()["DRAFT"] == "tenant-model"
    finally:
        MODEL_OVERRIDES.reset(tok)


# ---- B: RBAC ----

def test_invalid_role_rejected():
    client = TestClient(create_app())
    r = client.post("/v1/auth/token", json={"tenant_id": str(uuid4()), "role": "superuser"})
    assert r.status_code == 400


def test_role_gate_blocks_non_staff(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    client = TestClient(create_app())
    utok = client.post("/v1/auth/token", json={"tenant_id": str(uuid4()), "role": "user"}).json()["access_token"]
    r = client.get(f"/v1/metrics?tenant_id={uuid4()}", headers={"Authorization": f"Bearer {utok}"})
    assert r.status_code == 403


def test_role_gate_allows_admin(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    client = TestClient(create_app())
    atok = client.post("/v1/auth/token", json={"tenant_id": str(uuid4()), "role": "admin"}).json()["access_token"]
    r = client.get(f"/v1/metrics?tenant_id={uuid4()}", headers={"Authorization": f"Bearer {atok}"})
    assert r.status_code != 403
