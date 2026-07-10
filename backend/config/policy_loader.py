"""
Policy config loader.

Per PRD Section 2.6 / 3.2: the Policy Engine is driven by a tenant PolicyConfig.
This loader reads a named policy profile (YAML) and builds a PolicyConfig.
Phase 1 is single-tenant, so the 'default' profile is used unless a query's
domain maps to a stricter profile (e.g. 'medical', 'high_risk').
"""
from pathlib import Path
from functools import lru_cache
from dataclasses import fields, replace

import yaml

from backend.models.policy import PolicyConfig

_PROFILE_DIR = Path(__file__).parent / "policy_profiles"
_FIELD_TYPES = {f.name: f.type for f in fields(PolicyConfig)}
_VALID_FIELDS = set(_FIELD_TYPES)

# Numeric thresholds the auto-calibration loop is allowed to tune, with safe bounds.
CALIBRATABLE_FIELDS = {
    "minimum_evidence_count": (1, 5),
    "minimum_trust_score": (0.3, 0.95),
    "minimum_freshness_score": (0.0, 0.95),
    "minimum_claim_support_ratio": (0.5, 0.99),
    "qualified_claim_support_floor": (0.3, 0.9),
    "max_contradicted_claim_ratio": (0.0, 0.3),
}

# Domain hints that should escalate to a stricter policy profile.
_DOMAIN_PROFILE_MAP = {
    "medical": "medical",
    "health": "medical",
    "legal": "legal",
    "law": "legal",
    "financial": "financial",
    "finance": "financial",
}


@lru_cache(maxsize=16)
def load_policy_config(profile: str = "default") -> PolicyConfig:
    """Load a PolicyConfig from a YAML profile. Falls back to defaults if missing."""
    path = _PROFILE_DIR / f"{profile}.yaml"
    if not path.exists():
        # Unknown profile — fall back to default file, then hardcoded defaults.
        path = _PROFILE_DIR / "default.yaml"
        if not path.exists():
            return PolicyConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Keep only keys that map to PolicyConfig fields (ignore 'profile', 'description').
    kwargs = {k: v for k, v in raw.items() if k in _VALID_FIELDS}
    return PolicyConfig(**kwargs)


def apply_policy_overrides(config: PolicyConfig, overrides: dict) -> PolicyConfig:
    """Return a copy of `config` with any valid, in-bounds numeric overrides applied."""
    if not overrides:
        return config
    clean = {}
    for key, (lo, hi) in CALIBRATABLE_FIELDS.items():
        if key not in overrides:
            continue
        try:
            val = max(lo, min(hi, float(overrides[key])))
        except (TypeError, ValueError):
            continue
        clean[key] = int(round(val)) if key == "minimum_evidence_count" else val
    return replace(config, **clean) if clean else config


def clamp_calibratable(key: str, value: float) -> float:
    """Clamp a calibratable field to its safe bounds."""
    lo, hi = CALIBRATABLE_FIELDS[key]
    return max(lo, min(hi, value))


def resolve_profile_for_domain(domain_hint: str | None) -> str:
    """Map a query domain hint to a policy profile name."""
    if not domain_hint:
        return "default"
    return _DOMAIN_PROFILE_MAP.get(domain_hint.strip().lower(), "default")
