import numpy as np
import pytest

from ml.phase3a import (
    BETH_FEATURES, BETH_FORBIDDEN, ENGINE_SPEC, MAX_OPERATIONAL_FPR,
    NETWORK_SPEC, operational_threshold, validate_feature_contract,
)


def test_validated_features_exclude_forbidden_variables():
    for spec in (ENGINE_SPEC, NETWORK_SPEC):
        assert not set(spec.features) & set(spec.forbidden)
        assert spec.target not in spec.features
    assert not set(BETH_FEATURES) & set(BETH_FORBIDDEN)
    assert "evil" not in BETH_FEATURES


def test_feature_contract_rejects_unexpected_or_forbidden_columns():
    spec = NETWORK_SPEC
    valid = list(spec.features) + [spec.target]
    validate_feature_contract(valid, spec.features, spec.target, spec.forbidden)
    with pytest.raises(ValueError, match="Unexpected"):
        validate_feature_contract(valid + ["device_id"], spec.features, spec.target, spec.forbidden)
    with pytest.raises(ValueError, match="Forbidden"):
        validate_feature_contract(valid + ["device_id"], spec.features + ("device_id",), spec.target, spec.forbidden)


def test_operational_threshold_respects_false_positive_limit():
    y = np.array([0] * 100 + [1] * 20)
    scores = np.array(list(np.linspace(0, 0.6, 100)) + list(np.linspace(0.4, 1, 20)))
    threshold = operational_threshold(y, scores)
    predictions = scores >= threshold
    fpr = predictions[:100].mean()
    assert fpr <= MAX_OPERATIONAL_FPR
