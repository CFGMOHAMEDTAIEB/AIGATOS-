"""Train Phase 3A advisory reference models from prepared datasets only."""

from __future__ import annotations

import json
import pickle
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import matplotlib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(r"D:\AIGATOS")
DATA_ROOT = ROOT / "datasets" / "processed"
MODEL_ROOT = ROOT / "models"
REPORT_ROOT = ROOT / "reports" / "ml"
SEED = 20260922
MAX_OPERATIONAL_FPR = 0.05


@dataclass(frozen=True)
class DatasetSpec:
    slug: str
    target: str
    features: tuple[str, ...]
    forbidden: tuple[str, ...]
    subgroup_features: tuple[str, ...]


ENGINE_SPEC = DatasetSpec(
    slug="automotive-engine-health",
    target="engine_condition",
    features=(
        "engine_rpm", "lub_oil_pressure", "fuel_pressure", "coolant_pressure",
        "lub_oil_temp", "coolant_temp",
    ),
    forbidden=("engine_condition",),
    subgroup_features=("engine_rpm", "coolant_temp"),
)

NETWORK_SPEC = DatasetSpec(
    slug="wireless-network-slicing",
    target="network_slice_failure",
    features=(
        "traffic_load_bps", "traffic_type", "network_utilization", "latency_ms",
        "packet_loss_rate", "signal_strength_dbm", "bandwidth_utilization",
        "device_type", "region", "time_of_day", "weather_conditions",
    ),
    forbidden=(
        "network_slice_failure", "device_id", "network_slice_id", "timestamp",
        "network_failure_count", "overload_status", "qos_metric_throughput",
    ),
    subgroup_features=("traffic_type", "device_type", "region", "time_of_day"),
)

BETH_FEATURES = ("process_name", "event_id", "event_name", "args_num", "return_value")
BETH_FORBIDDEN = (
    "evil", "sus", "timestamp", "host_name", "process_id", "thread_id",
    "parent_process_id", "user_id", "mount_namespace", "stack_addresses", "args",
)


def validate_feature_contract(columns: list[str], features: tuple[str, ...], target: str, forbidden: tuple[str, ...]) -> None:
    missing = sorted(set(features + (target,)) - set(columns))
    if missing:
        raise ValueError(f"Missing validated columns: {missing}")
    leaked = sorted(set(features) & set(forbidden))
    if leaked:
        raise ValueError(f"Forbidden variables in feature list: {leaked}")
    extras = sorted(set(columns) - set(features) - {target})
    if extras:
        raise ValueError(f"Unexpected prepared columns: {extras}")


def operational_threshold(y_true: np.ndarray, scores: np.ndarray, max_fpr: float = MAX_OPERATIONAL_FPR) -> float:
    fpr, tpr, thresholds = roc_curve(y_true, scores)
    valid = [
        (float(t), float(r), float(fp))
        for fp, r, t in zip(fpr, tpr, thresholds)
        if fp <= max_fpr and np.isfinite(t)
    ]
    if not valid:
        return float(np.nextafter(np.max(scores), np.inf))
    valid.sort(key=lambda item: (item[1], -item[2], -item[0]), reverse=True)
    return valid[0][0]


def classification_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = (scores >= threshold).astype(int)
    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    return {
        "threshold": float(threshold),
        "confusion_matrix": matrix.tolist(),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, scores)),
        "pr_auc": float(average_precision_score(y_true, scores)),
        "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
        "recall_at_operational_threshold": float(tp / (tp + fn)) if tp + fn else 0.0,
        "support": int(len(y_true)),
        "positive_rate": float(np.mean(y_true)),
    }


def _score(model: BaseEstimator, frame: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(frame)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        raw = np.asarray(model.decision_function(frame), dtype=float)
        return 1 / (1 + np.exp(-np.clip(raw, -30, 30)))
    return np.asarray(model.predict(frame), dtype=float)


def _timed_scores(model: BaseEstimator, frame: pd.DataFrame) -> tuple[np.ndarray, float]:
    start = time.perf_counter()
    scores = _score(model, frame)
    return scores, time.perf_counter() - start


def _model_bytes(model: Any) -> int:
    return len(pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))


def _plot_evaluation(dataset: str, name: str, y: np.ndarray, scores: np.ndarray, metrics: dict) -> None:
    directory = REPORT_ROOT / dataset
    directory.mkdir(parents=True, exist_ok=True)
    matrix = np.asarray(metrics["confusion_matrix"])
    fig, axis = plt.subplots(figsize=(4.5, 4))
    image = axis.imshow(matrix, cmap="Blues")
    for (row, column), value in np.ndenumerate(matrix):
        axis.text(column, row, str(value), ha="center", va="center")
    axis.set(title=f"{dataset} — {name}", xlabel="Predicted", ylabel="Actual", xticks=[0, 1], yticks=[0, 1])
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    fig.savefig(directory / "confusion_matrix.png", dpi=150)
    plt.close(fig)

    fpr, tpr, _ = roc_curve(y, scores)
    precision, recall, _ = precision_recall_curve(y, scores)
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    axes[0].plot(fpr, tpr, label=f"AUC={metrics['roc_auc']:.3f}")
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="grey")
    axes[0].set(title="ROC", xlabel="FPR", ylabel="Recall")
    axes[0].legend()
    axes[1].plot(recall, precision, label=f"AP={metrics['pr_auc']:.3f}")
    axes[1].set(title="Precision–Recall", xlabel="Recall", ylabel="Precision")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(directory / "roc_pr_curves.png", dpi=150)
    plt.close(fig)


def _subgroup_metrics(y: np.ndarray, scores: np.ndarray, threshold: float, groups: pd.Series, limit: int = 12) -> list[dict]:
    result = []
    for group in groups.astype(str).value_counts().head(limit).index:
        mask = groups.astype(str).to_numpy() == group
        group_y = y[mask]
        if len(group_y) < 10 or len(np.unique(group_y)) < 2:
            result.append({"group": group, "support": int(mask.sum()), "positive_rate": float(np.mean(group_y))})
            continue
        item = classification_metrics(group_y, scores[mask], threshold)
        item["group"] = group
        result.append(item)
    return result


def _feature_effects(model: BaseEstimator, name: str, features: tuple[str, ...], x_validation: pd.DataFrame, y_validation: np.ndarray) -> list[dict]:
    if name == "logistic_regression":
        values = np.abs(model.named_steps["model"].coef_[0])
    elif name == "random_forest":
        values = model.feature_importances_
    else:
        sample = x_validation.sample(min(len(x_validation), 2000), random_state=SEED)
        y_sample = y_validation[sample.index.to_numpy()]
        values = permutation_importance(
            model, sample, y_sample, scoring="average_precision", n_repeats=5,
            random_state=SEED, n_jobs=-1,
        ).importances_mean
    return sorted(
        ({"feature": feature, "effect": float(value)} for feature, value in zip(features, values)),
        key=lambda item: abs(item["effect"]), reverse=True,
    )


def train_supervised(spec: DatasetSpec) -> dict:
    splits = {name: pd.read_csv(DATA_ROOT / spec.slug / f"{name}.csv") for name in ("train", "validation", "test")}
    for frame in splits.values():
        validate_feature_contract(list(frame.columns), spec.features, spec.target, spec.forbidden)
    x_train, y_train = splits["train"].loc[:, list(spec.features)], splits["train"][spec.target].to_numpy()
    x_validation, y_validation = splits["validation"].loc[:, list(spec.features)], splits["validation"][spec.target].to_numpy()

    candidates: dict[str, BaseEstimator] = {
        "dummy_prior": DummyClassifier(strategy="prior"),
        "logistic_regression": Pipeline([
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=SEED)),
        ]),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample",
            random_state=SEED, n_jobs=-1,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=250, learning_rate=0.05, l2_regularization=0.1,
            class_weight="balanced", random_state=SEED,
        ),
    }
    validation_results = {}
    fitted = {}
    for name, model in candidates.items():
        start = time.perf_counter()
        model.fit(x_train, y_train)
        training_seconds = time.perf_counter() - start
        scores, inference_seconds = _timed_scores(model, x_validation)
        threshold = operational_threshold(y_validation, scores)
        metrics = classification_metrics(y_validation, scores, threshold)
        metrics.update({
            "training_seconds": training_seconds,
            "inference_seconds": inference_seconds,
            "inference_rows_per_second": len(x_validation) / inference_seconds if inference_seconds else None,
            "model_size_bytes": _model_bytes(model),
        })
        validation_results[name] = metrics
        fitted[name] = model

    eligible = [name for name in candidates if name != "dummy_prior"]
    selected = max(eligible, key=lambda name: (validation_results[name]["pr_auc"], validation_results[name]["f1"]))
    baseline = validation_results["dummy_prior"]
    selected_metrics = validation_results[selected]
    beats_baseline = selected_metrics["pr_auc"] > baseline["pr_auc"] and selected_metrics["f1"] >= baseline["f1"]
    model_path = None
    test_result = None
    effects = []
    subgroups = {}
    if beats_baseline:
        model = fitted[selected]
        model_dir = MODEL_ROOT / spec.slug
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "model.joblib"
        joblib.dump({
            "model": model, "features": spec.features, "target": spec.target,
            "threshold": selected_metrics["threshold"], "seed": SEED,
            "advisory_only": True,
        }, model_path)
        x_test = splits["test"].loc[:, list(spec.features)]
        y_test = splits["test"][spec.target].to_numpy()
        test_scores, inference_seconds = _timed_scores(model, x_test)
        test_result = classification_metrics(y_test, test_scores, selected_metrics["threshold"])
        test_result.update({
            "inference_seconds": inference_seconds,
            "inference_rows_per_second": len(x_test) / inference_seconds if inference_seconds else None,
            "saved_model_size_bytes": model_path.stat().st_size,
        })
        effects = _feature_effects(model, selected, spec.features, x_validation, y_validation)
        for feature in spec.subgroup_features:
            if pd.api.types.is_numeric_dtype(splits["test"][feature]) and splits["test"][feature].nunique() > 12:
                groups = pd.qcut(splits["test"][feature], q=4, duplicates="drop").astype(str)
            else:
                groups = splits["test"][feature].astype(str)
            subgroups[feature] = _subgroup_metrics(y_test, test_scores, selected_metrics["threshold"], groups)
        _plot_evaluation(spec.slug, selected, y_test, test_scores, test_result)

    report = {
        "dataset": spec.slug,
        "seed": SEED,
        "selection_rule": "Highest validation PR-AUC, then F1; save only when PR-AUC exceeds Dummy and F1 is not worse.",
        "operational_threshold_rule": f"Maximum validation recall with false-positive rate <= {MAX_OPERATIONAL_FPR:.0%}.",
        "features": list(spec.features),
        "forbidden_variables": list(spec.forbidden),
        "validation": validation_results,
        "selected_model": selected if beats_baseline else None,
        "beats_baseline": beats_baseline,
        "model_path": str(model_path) if model_path else None,
        "test_once": test_result,
        "feature_effects": effects,
        "subgroup_analysis": subgroups,
        "advisory_only": True,
    }
    return report


class StatisticalAnomalyBaseline:
    def fit(self, frame: pd.DataFrame) -> "StatisticalAnomalyBaseline":
        self.rows_ = len(frame)
        self.process_frequency_ = frame["process_name"].value_counts().to_dict()
        self.event_frequency_ = frame["event_name"].value_counts().to_dict()
        self.numeric_ = {}
        for column in ("event_id", "args_num", "return_value"):
            median = float(frame[column].median())
            mad = float(np.median(np.abs(frame[column].to_numpy(dtype=float) - median))) or 1.0
            self.numeric_[column] = (median, mad)
        training_scores = self.raw_score(frame.sample(min(len(frame), 100_000), random_state=SEED))
        self.low_, self.high_ = np.quantile(training_scores, [0.01, 0.99])
        if self.high_ <= self.low_:
            self.high_ = self.low_ + 1.0
        return self

    def raw_score(self, frame: pd.DataFrame) -> np.ndarray:
        process = frame["process_name"].map(self.process_frequency_).fillna(0).to_numpy()
        event = frame["event_name"].map(self.event_frequency_).fillna(0).to_numpy()
        score = -np.log((process + 1) / (self.rows_ + len(self.process_frequency_)))
        score += -np.log((event + 1) / (self.rows_ + len(self.event_frequency_)))
        for column, (median, mad) in self.numeric_.items():
            score += np.minimum(np.abs(frame[column].to_numpy(dtype=float) - median) / mad, 10.0)
        return score

    def score(self, frame: pd.DataFrame) -> np.ndarray:
        return np.clip((self.raw_score(frame) - self.low_) / (self.high_ - self.low_), 0, 1)


def _beth_isolation_pipeline() -> Pipeline:
    categorical = ["process_name", "event_name"]
    numeric = ["event_id", "args_num", "return_value"]
    preprocess = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore", min_frequency=10), categorical),
        ("numeric", StandardScaler(), numeric),
    ])
    return Pipeline([
        ("preprocess", preprocess),
        ("model", IsolationForest(
            n_estimators=200, max_samples=2048, contamination="auto",
            random_state=SEED, n_jobs=-1,
        )),
    ])


def _isolation_scores(model: Pipeline, frame: pd.DataFrame, low: float, high: float) -> np.ndarray:
    raw = -model.decision_function(frame)
    return np.clip((raw - low) / (high - low), 0, 1)


def _distribution(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    counts = frame[column].value_counts().sort_index()
    return {
        "counts": {str(key): int(value) for key, value in counts.items()},
        "rates": {str(key): float(value / len(frame)) for key, value in counts.items()},
    }


def train_beth() -> dict:
    splits = {name: pd.read_csv(DATA_ROOT / "beth" / f"{name}.csv") for name in ("train", "validation", "test")}
    expected = set(BETH_FEATURES) | {"sus", "evil"}
    for frame in splits.values():
        if set(frame.columns) != expected:
            raise ValueError("BETH prepared schema differs from the validated feature contract")
        if set(BETH_FEATURES) & set(BETH_FORBIDDEN):
            raise ValueError("Forbidden BETH variable in features")
    shift = {
        split: {target: _distribution(frame, target) for target in ("sus", "evil")}
        for split, frame in splits.items()
    }
    x_train = splits["train"].loc[:, list(BETH_FEATURES)]
    x_validation = splits["validation"].loc[:, list(BETH_FEATURES)]
    y_validation = splits["validation"]["sus"].to_numpy()

    baseline = StatisticalAnomalyBaseline()
    start = time.perf_counter()
    baseline.fit(x_train)
    baseline_train_seconds = time.perf_counter() - start
    baseline_scores, baseline_inference = _timed_custom(baseline.score, x_validation)
    baseline_threshold = operational_threshold(y_validation, baseline_scores)
    baseline_metrics = classification_metrics(y_validation, baseline_scores, baseline_threshold)
    baseline_metrics.update({
        "training_seconds": baseline_train_seconds,
        "inference_seconds": baseline_inference,
        "inference_rows_per_second": len(x_validation) / baseline_inference,
        "model_size_bytes": _model_bytes(baseline),
    })

    isolation = _beth_isolation_pipeline()
    train_sample = x_train.sample(min(len(x_train), 200_000), random_state=SEED)
    start = time.perf_counter()
    isolation.fit(train_sample)
    isolation_train_seconds = time.perf_counter() - start
    calibration_raw = -isolation.decision_function(train_sample)
    isolation_low, isolation_high = np.quantile(calibration_raw, [0.01, 0.99])
    if isolation_high <= isolation_low:
        isolation_high = isolation_low + 1.0
    isolation_scores, isolation_inference = _timed_custom(
        lambda frame: _isolation_scores(isolation, frame, isolation_low, isolation_high),
        x_validation,
    )
    isolation_threshold = operational_threshold(y_validation, isolation_scores)
    isolation_metrics = classification_metrics(y_validation, isolation_scores, isolation_threshold)
    isolation_metrics.update({
        "training_seconds": isolation_train_seconds,
        "inference_seconds": isolation_inference,
        "inference_rows_per_second": len(x_validation) / isolation_inference,
        "model_size_bytes": _model_bytes(isolation),
        "fit_rows": len(train_sample),
    })

    beats_baseline = isolation_metrics["pr_auc"] > baseline_metrics["pr_auc"] and isolation_metrics["f1"] >= baseline_metrics["f1"]
    selected = "isolation_forest" if beats_baseline else "statistical_baseline"
    selected_score_function = (
        lambda frame: _isolation_scores(isolation, frame, isolation_low, isolation_high)
    ) if beats_baseline else baseline.score
    selected_threshold = isolation_threshold if beats_baseline else baseline_threshold
    model_path = None
    if beats_baseline:
        model_dir = MODEL_ROOT / "beth"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "model.joblib"
        joblib.dump({
            "model": isolation, "features": BETH_FEATURES, "target": "sus",
            "threshold": selected_threshold, "seed": SEED, "advisory_only": True,
            "score_calibration": {"low": float(isolation_low), "high": float(isolation_high)},
            "scope": "generic system-log anomalies, not automotive OTA anomalies",
        }, model_path)

    x_test = splits["test"].loc[:, list(BETH_FEATURES)]
    y_test = splits["test"]["sus"].to_numpy()
    test_scores, test_inference = _timed_custom(selected_score_function, x_test)
    test_metrics = classification_metrics(y_test, test_scores, selected_threshold)
    test_metrics.update({
        "inference_seconds": test_inference,
        "inference_rows_per_second": len(x_test) / test_inference,
        "saved_model_size_bytes": model_path.stat().st_size if model_path else None,
    })
    subgroup = {
        column: _subgroup_metrics(y_test, test_scores, selected_threshold, splits["test"][column], limit=10)
        for column in ("process_name", "event_name")
    }
    _plot_evaluation("beth", selected, y_test, test_scores, test_metrics)

    return {
        "dataset": "beth",
        "seed": SEED,
        "scope": "Generic system-log anomaly experiment; not an automotive or OTA anomaly detector.",
        "target": "sus",
        "evil_supervised_classifier_prohibited": True,
        "distribution_shift": shift,
        "features": list(BETH_FEATURES),
        "forbidden_variables": list(BETH_FORBIDDEN),
        "validation": {
            "statistical_baseline": baseline_metrics,
            "isolation_forest": isolation_metrics,
        },
        "selected_method": selected,
        "saved_model": str(model_path) if model_path else None,
        "beats_baseline": beats_baseline,
        "operational_threshold_rule": f"Maximum validation recall with false-positive rate <= {MAX_OPERATIONAL_FPR:.0%}.",
        "test_once": test_metrics,
        "subgroup_analysis": subgroup,
        "risks": [
            "evil has zero positives in train and validation but is dominant in test; no supervised evil model is valid",
            "sus prevalence also shifts sharply between splits",
            "timestamps and host identifiers were removed, preventing direct leakage but also limiting temporal diagnostics",
            "results describe generic system logs only and cannot establish an OTA root cause",
        ],
        "advisory_only": True,
    }


def _timed_custom(function, frame: pd.DataFrame) -> tuple[np.ndarray, float]:
    start = time.perf_counter()
    values = np.asarray(function(frame), dtype=float)
    return values, time.perf_counter() - start


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def _comparison_rows(reports: list[dict]) -> list[dict]:
    rows = []
    for report in reports:
        for model, metrics in report["validation"].items():
            rows.append({
                "dataset": report["dataset"], "model": model, "split": "validation",
                **{key: metrics[key] for key in (
                    "precision", "recall", "f1", "roc_auc", "pr_auc",
                    "false_positive_rate", "recall_at_operational_threshold",
                    "training_seconds", "inference_seconds", "model_size_bytes",
                )},
            })
        selected = report.get("selected_model") or report.get("selected_method")
        if report.get("test_once"):
            metrics = report["test_once"]
            rows.append({
                "dataset": report["dataset"], "model": selected, "split": "test_once",
                **{key: metrics.get(key) for key in (
                    "precision", "recall", "f1", "roc_auc", "pr_auc",
                    "false_positive_rate", "recall_at_operational_threshold",
                    "inference_seconds",
                )},
                "training_seconds": None,
                "model_size_bytes": metrics.get("saved_model_size_bytes"),
            })
    return rows


def main() -> None:
    np.random.seed(SEED)
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    reports = [train_supervised(ENGINE_SPEC), train_supervised(NETWORK_SPEC), train_beth()]
    for report in reports:
        directory = REPORT_ROOT / report["dataset"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "metrics.json").write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    rows = _comparison_rows(reports)
    pd.DataFrame(rows).to_csv(REPORT_ROOT / "model_comparison.csv", index=False)
    summary = {
        "phase": "3A",
        "seed": SEED,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "datasets": [report["dataset"] for report in reports],
        "selected": {
            report["dataset"]: report.get("selected_model") or report.get("selected_method")
            for report in reports
        },
        "llm_calls": 0,
        "ota_actions": 0,
        "advisory_only": True,
    }
    (REPORT_ROOT / "phase3a_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
