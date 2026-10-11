"""Risk model configuration: criteria, default weights, classes, actions, calibration.

The model is data, not code. It is loaded from YAML and validated here so that
criteria, weights, thresholds and rules can be changed without touching the
agents.

Weights
-------
Weights are never hard-coded. The YAML defines *default* weights (dimension
weight x factor weight within the dimension). They are exposed as a
:class:`WeightSet` of *effective factor weights* (one number per factor,
summing to 1). The scoring engine only ever consumes a ``WeightSet``, so the
default set, a material-group-specific set or a calibrated set are fully
interchangeable.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_MODEL_RESOURCE = "default_risk_model.yaml"
GLOBAL_SCOPE = "global"


class RatingScale(BaseModel):
    min: int = 1
    max: int = 5

    @model_validator(mode="after")
    def _check_range(self) -> RatingScale:
        if self.max <= self.min:
            raise ValueError("rating_scale.max must be greater than rating_scale.min")
        return self


class FactorConfig(BaseModel):
    key: str
    label: str
    description: str = ""
    weight: float = Field(gt=0, description="Default weight relative to the other factors of the dimension")
    source: str = Field(description="Which indicator/tool provides the rating for this factor")


class DimensionConfig(BaseModel):
    key: str
    label: str
    description: str = ""
    weight: float = Field(gt=0, description="Default weight relative to the other dimensions")
    factors: list[FactorConfig] = Field(min_length=1)


class WeightSet(BaseModel):
    """Effective factor weights used for one scoring run.

    ``factor_weights[f]`` is the share of factor *f* in the overall score
    (= dimension weight x factor weight within the dimension). Values are
    non-negative and sum to 1. Dimension weights are derived, not stored.
    """

    scope: str = Field(default=GLOBAL_SCOPE, description="'global' or a material group key")
    origin: Literal["default", "material_group_default", "calibrated", "manual"] = "default"
    factor_weights: dict[str, float]
    version: int | None = Field(default=None, description="Version in the weight store, if persisted")
    note: str = ""

    @model_validator(mode="after")
    def _normalise(self) -> WeightSet:
        if any(w < 0 for w in self.factor_weights.values()):
            raise ValueError("weights must be non-negative")
        total = sum(self.factor_weights.values())
        if total <= 0:
            raise ValueError("weights must not all be zero")
        self.factor_weights = {k: v / total for k, v in self.factor_weights.items()}
        return self

    def dimension_weights(self, model: RiskModelConfig) -> dict[str, float]:
        return {d.key: sum(self.factor_weights.get(f.key, 0.0) for f in d.factors) for d in model.dimensions}

    def rounded(self, digits: int = 4) -> dict[str, float]:
        return {k: round(v, digits) for k, v in self.factor_weights.items()}


class RiskClassConfig(BaseModel):
    key: str
    label: str
    min_score: float = Field(ge=0, le=100)


class EscalationRule(BaseModel):
    factor: str
    min_rating: int
    floor_class: str
    reason: str = ""


class ClassActions(BaseModel):
    review_cycle: str
    actions: list[str]


class DimensionTrigger(BaseModel):
    dimension: str
    min_score: float = Field(ge=0, le=100)
    action: str


class CalibrationSettings(BaseModel):
    """Controls the expert-label calibration (see docs/calibration.md)."""

    enabled: bool = False
    method: Literal["constrained_least_squares"] = "constrained_least_squares"
    min_labels: int = Field(default=8, ge=2, description="Minimum labelled suppliers with complete data")
    regularization: float = Field(default=0.05, ge=0, description="Pull towards the prior weights (ridge)")
    min_factor_weight: float = Field(default=0.02, ge=0, description="Lower bound per factor weight")
    min_improvement: float = Field(default=0.05, ge=0, le=1, description="Relative MSE reduction needed to accept")
    acceptance: Literal["cross_validated", "in_sample"] = Field(
        default="cross_validated",
        description=(
            "Basis of the acceptance test. 'cross_validated' compares out-of-fold MSE of the refitted "
            "weights with the prior weights and rejects fits that only memorise noise; 'in_sample' "
            "compares training MSE only (legacy behaviour, no protection against overfitting)."
        ),
    )
    cv_folds: int = Field(default=5, ge=2, description="Folds for cross-validated acceptance")
    cv_repeats: int = Field(default=3, ge=1, description="Repeats with reshuffled folds (deterministic)")
    level_bias_threshold: float = Field(
        default=5.0, ge=0,
        description="Flag a level offset if labels differ from scores by at least this many points on average",
    )
    level_bias_min_t: float = Field(default=2.0, ge=0, description="...and the offset is at least this many standard errors")
    level_bias_action: Literal["review", "warn"] = Field(
        default="review",
        description="'review': never auto-apply weights calibrated on level-biased labels; 'warn': report only",
    )
    auto_apply: bool = Field(default=True, description="Re-score with accepted weights; else only propose them")


class RiskModelConfig(BaseModel):
    """Complete, validated description of a risk model."""

    name: str
    version: str
    rating_scale: RatingScale = RatingScale()
    dimensions: list[DimensionConfig] = Field(min_length=1)
    # Optional default weights per material group: {group: {factor: weight}}.
    # Factors not listed keep their global default weight before re-normalisation.
    material_group_weights: dict[str, dict[str, float]] = {}
    risk_classes: list[RiskClassConfig] = Field(min_length=1)
    escalation_rules: list[EscalationRule] = []
    min_data_completeness: float = Field(default=0.75, ge=0, le=1)
    actions: dict[str, ClassActions] = {}
    dimension_triggers: list[DimensionTrigger] = []
    calibration: CalibrationSettings = CalibrationSettings()

    @model_validator(mode="after")
    def _validate(self) -> RiskModelConfig:
        factor_keys = self.factor_keys()
        if len(factor_keys) != len(set(factor_keys)):
            raise ValueError("factor keys must be unique across all dimensions")

        self.risk_classes.sort(key=lambda c: c.min_score)
        if self.risk_classes[0].min_score != 0:
            raise ValueError("the lowest risk class must start at min_score 0")
        class_keys = {c.key for c in self.risk_classes}
        dim_keys = {d.key for d in self.dimensions}

        for group, weights in self.material_group_weights.items():
            unknown = set(weights) - set(factor_keys)
            if unknown:
                raise ValueError(f"material group '{group}' references unknown factors {sorted(unknown)}")
        for rule in self.escalation_rules:
            if rule.factor not in factor_keys:
                raise ValueError(f"escalation rule references unknown factor '{rule.factor}'")
            if rule.floor_class not in class_keys:
                raise ValueError(f"escalation rule references unknown class '{rule.floor_class}'")
        for trig in self.dimension_triggers:
            if trig.dimension not in dim_keys:
                raise ValueError(f"trigger references unknown dimension '{trig.dimension}'")
        for key in self.actions:
            if key not in class_keys:
                raise ValueError(f"actions defined for unknown class '{key}'")
        if self.calibration.min_factor_weight * len(factor_keys) > 1:
            raise ValueError("calibration.min_factor_weight x number of factors must be <= 1")
        return self

    # --- helpers -------------------------------------------------------------

    def factor_keys(self) -> list[str]:
        return [f.key for d in self.dimensions for f in d.factors]

    def dimension_of(self, factor_key: str) -> str:
        for d in self.dimensions:
            if any(f.key == factor_key for f in d.factors):
                return d.key
        raise KeyError(factor_key)

    def class_rank(self, class_key: str) -> int:
        return [c.key for c in self.risk_classes].index(class_key)

    def default_weights(self, material_group: str | None = None) -> WeightSet:
        """Default weights from the config, optionally with a material group overlay."""
        dim_total = sum(d.weight for d in self.dimensions)
        weights: dict[str, float] = {}
        for d in self.dimensions:
            fac_total = sum(f.weight for f in d.factors)
            for f in d.factors:
                weights[f.key] = d.weight / dim_total * f.weight / fac_total

        if material_group and material_group in self.material_group_weights:
            weights |= self.material_group_weights[material_group]
            return WeightSet(scope=material_group, origin="material_group_default", factor_weights=weights)
        return WeightSet(scope=GLOBAL_SCOPE, origin="default", factor_weights=weights)


def load_risk_model(path: str | Path | None = None) -> RiskModelConfig:
    """Load a risk model from ``path`` or fall back to the bundled default template."""
    if path is None:
        text = (
            resources.files("supplier_risk_agent.config")
            .joinpath(DEFAULT_MODEL_RESOURCE)
            .read_text(encoding="utf-8")
        )
    else:
        text = Path(path).read_text(encoding="utf-8")
    return RiskModelConfig.model_validate(yaml.safe_load(text))
