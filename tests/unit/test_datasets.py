"""Golden evaluation datasets (3 types)."""
import pytest

from backend.services.evaluation.datasets import list_datasets, load_dataset

_VALID = {"VERIFIED", "QUALIFIED", "REFUSED", "ESCALATED"}


def test_three_dataset_types_present():
    names = list_datasets()
    for expected in ("factual", "unanswerable", "conflicting"):
        assert expected in names


def test_dataset_case_shapes():
    for name in ("factual", "unanswerable", "conflicting"):
        d = load_dataset(name)
        assert d["name"] and d["cases"]
        for c in d["cases"]:
            assert c["id"] and c["query"]
            assert c["expected_decision"] in _VALID


def test_unknown_dataset_raises():
    with pytest.raises(FileNotFoundError):
        load_dataset("does-not-exist")
