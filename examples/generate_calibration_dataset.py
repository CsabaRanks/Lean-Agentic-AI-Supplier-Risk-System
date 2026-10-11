"""Generate a synthetic, labelled supplier portfolio for calibration demos.

The "expert labels" are produced from a hidden weighting that differs from the
default template (the simulated category managers care more about business
impact and single sourcing, less about ESG score) plus rounding and noise.
Calibration should therefore move the weights in that direction and reduce
the MSE. Everything is fictional and reproducible (fixed seed).

    python examples/generate_calibration_dataset.py  # writes data/calibration_portfolio.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from supplier_risk_agent import SupplierProfile, WeightSet, load_risk_model
from supplier_risk_agent.tools import aggregate, score_factors

SEED = 42
N_SUPPLIERS = 36
GROUPS = ["plastics", "metal_parts", "electronics"]
OUT = Path(__file__).resolve().parents[1] / "data" / "calibration_portfolio.json"

# Hidden "expert" weighting (effective factor weights, re-normalised).
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


def random_supplier(rng: random.Random, i: int) -> SupplierProfile:
    return SupplierProfile(
        supplier_id=f"CAL-{i:03d}",
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


def main() -> None:
    rng = random.Random(SEED)
    model = load_risk_model()
    hidden = WeightSet(origin="manual", factor_weights=HIDDEN_EXPERT_WEIGHTS)

    records = []
    for i in range(1, N_SUPPLIERS + 1):
        s = random_supplier(rng, i)
        true_score = aggregate(score_factors(s, model, hidden), model).overall_score
        noisy = true_score + rng.gauss(0, 4)
        s.expert_risk_score = float(min(100, max(0, 5 * round(noisy / 5))))  # experts think in 5-point steps
        records.append(s.model_dump(exclude_none=True))

    # A few suppliers without an expert label: scored, but not used for calibration.
    for r in records[-4:]:
        r.pop("expert_risk_score", None)

    OUT.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} suppliers to {OUT}")


if __name__ == "__main__":
    main()
