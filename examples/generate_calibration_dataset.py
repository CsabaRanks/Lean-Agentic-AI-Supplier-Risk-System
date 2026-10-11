"""Generate a synthetic, labelled supplier portfolio for calibration demos.

The "expert labels" are produced from a hidden weighting that differs from the
default template (the simulated category managers care more about business
impact and single sourcing, less about ESG score) plus rounding and noise.
Calibration should therefore move the weights in that direction and reduce
the MSE. Everything is fictional and reproducible (fixed seed).
Generator: ``supplier_risk_agent.tools.synthetic``.

    python examples/generate_calibration_dataset.py  # writes data/calibration_portfolio.json
"""

from __future__ import annotations

import json
from pathlib import Path

from supplier_risk_agent import load_risk_model
from supplier_risk_agent.tools.synthetic import synthetic_portfolio

SEED = 42
N_SUPPLIERS = 36
N_UNLABELLED = 4
OUT = Path(__file__).resolve().parents[1] / "data" / "calibration_portfolio.json"


def main() -> None:
    suppliers = synthetic_portfolio(N_SUPPLIERS, SEED, load_risk_model())
    records = [s.model_dump(exclude_none=True) for s in suppliers]

    # A few suppliers without an expert label: scored, but not used for calibration.
    for r in records[-N_UNLABELLED:]:
        r.pop("expert_risk_score", None)

    OUT.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} suppliers to {OUT}")


if __name__ == "__main__":
    main()
