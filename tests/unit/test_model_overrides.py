"""Per-tenant model registry — model resolution via the MODEL_OVERRIDES contextvar."""
from backend.orchestration.model_client import resolve_model, MODEL_OVERRIDES, _TASK_MODELS
from backend.config.settings import settings


def test_default_model_when_no_override():
    assert resolve_model("DRAFT") == _TASK_MODELS["DRAFT"]


def test_override_wins_for_that_task_only():
    token = MODEL_OVERRIDES.set({"DRAFT": "gpt-4o"})
    try:
        assert resolve_model("DRAFT") == "gpt-4o"
        # A task without an override still uses its default.
        assert resolve_model("VERIFY") == _TASK_MODELS["VERIFY"]
    finally:
        MODEL_OVERRIDES.reset(token)


def test_unknown_task_falls_back_to_default_llm():
    assert resolve_model("SOMETHING_ELSE") == settings.llm_model
