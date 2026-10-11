"""Synthetic, labelled supplier portfolios for calibration demos and validation.

Expert labels are produced from a *hidden* weighting that differs from the
default template, plus Gaussian noise and rounding to the 5-point steps
experts tend to use. Because the generating weights are known, it can be
checked whether calibration recovers them, which no field dataset allows.

Everything is fictional and reproducible for a given seed.
"""

from __future__ import annotations

import random

from ..models.config import RiskModelConfig, WeightSet
from ..models.domain import SupplierProfile
from .scoring import aggregate, score_factors

GROUPS = ["plastics", "metal_parts", "electronics"]

# Hidden "expert" weighting (effective factor weights): the simulated category
# managers care more about business impact and single sourcing, less about ESG.
HIDDEN_EXPERT_WEIGHTS = {
    "availability": 0.10,
    "switching_complexity": 0.10,
    "business_impact": 0.22,
    "credit_risk": 0.12,
    "insolvency_signals": 0.06,
    "country_risk": 0.12,
    "sourcing_strategy": 0.16,
    "transport_dependency": 0.04,
    "esg_rating": 0.03,
    "compliance_status": 0.05,
}


def hidden_weights() -> WeightSet:
    return WeightSet(origin="manual", factor_weights=HIDDEN_EXPERT_WEIGHTS, note="hidden generating weights")


def random_supplier(rng: random.Random, i: int, prefix: str = "CAL") -> SupplierProfile:
    return SupplierProfile(
        supplier_id=f"{prefix}-{i:03d}",
        name=f"Synthetic Supplier {i:03d}",
        material_group=GROUPS[i % len(GROUPS)],
        country=f"Region {rng.choice('ABCDE')}",
        annual_spend=round(rng.uniform(50_000, 3_000_000), -3),
        expert_ratings={k: rng.randint(1, 5) for k in ("availability", "switching_complexity", "business_impact")},
        indicators={
            "credit_score": rng.randint(20, 95),
            "distress_signals": rng.choices([0, 1, 2, 3], weights=[70, 18, 8, 4])[0],
            "country_risk_index": rng.randint(5, 90),
            "qualified_sources": rng.choice([1, 1, 2, 2, 3, 4]),
            "transport_mode": rng.choice(["road", "rail", "sea", "air"]),
            "intercontinental": rng.random() < 0.3,
            "esg_score": rng.randint(15, 90),
            "compliance_status": rng.choices(
                ["compliant", "minor_findings", "open_findings", "major_findings"], weights=[60, 20, 15, 5]
            )[0],
        },
    )


def synthetic_portfolio(
    n: int,
    seed: int,
    model: RiskModelConfig,
    hidden: WeightSet | None = None,
    noise_sd: float = 4.0,
    label_step: float = 5.0,
    prefix: str = "CAL",
) -> list[SupplierProfile]:
    """``n`` labelled synthetic suppliers.

    label = clip(step * round((true_score + N(0, noise_sd)) / step), 0, 100),
    where true_score is the model score under the hidden weighting.
    """
    rng = random.Random(seed)
    hidden = hidden or hidden_weights()
    suppliers = []
    for i in range(1, n + 1):
        s = random_supplier(rng, i, prefix)
        true_score = aggregate(score_factors(s, model, hidden), model).overall_score
        noisy = true_score + rng.gauss(0, noise_sd)
        label = label_step * round(noisy / label_step) if label_step else noisy
        s.expert_risk_score = float(min(100, max(0, label)))
        suppliers.append(s)
    return suppliers


def label_noise_floor(noise_sd: float = 4.0, label_step: float = 5.0) -> float:
    """Expected irreducible MSE of labels vs. true scores (noise + rounding), ignoring clipping."""
    return noise_sd**2 + (label_step**2 / 12 if label_step else 0.0)
