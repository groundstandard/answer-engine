"""
Policy config loader.

Per PRD Section 2.6 / 3.2: the Policy Engine is driven by a tenant PolicyConfig.
This loader reads a named policy profile (YAML) and builds a PolicyConfig.
Phase 1 is single-tenant, so the 'default' profile is used unless a query's
domain maps to a stricter profile (e.g. 'medical', 'high_risk').
"""
from pathlib import Path
from functools import lru_cache
from dataclasses import fields

import yaml

from backend.models.policy import PolicyConfig

_PROFILE_DIR = Path(__file__).parent / "policy_profiles"
_VALID_FIELDS = {f.name for f in fields(PolicyConfig)}

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


def resolve_profile_for_domain(domain_hint: str | None) -> str:
    """Map a query domain hint to a policy profile name."""
    if not domain_hint:
        return "default"
    return _DOMAIN_PROFILE_MAP.get(domain_hint.strip().lower(), "default")
