"""Assessment history: snapshots with a timestamp, to follow suppliers over time.

``HistoryStore`` appends one line per supplier and snapshot to
``<directory>/<view>.jsonl``. A snapshot records score (in the view's reading
direction), class, dimension scores, the weights used, and who approved it,
if anyone. The file is append-only and plain text, so it can be versioned,
inspected and imported elsewhere.

Snapshots are taken explicitly: CLI ``--history-dir``, the UI's "Save snapshot"
button, or automatically after a review decision in the UI. Recording every
recalculation while data is still being edited would only add noise.

Corrections and objections are kept next to the snapshots, also append-only:

* ``corrections.jsonl``: confirmed corrections with old and new values, kind
  (data correction or expert override), reason, time, the name typed by the
  user (not a verified identity), model and weight versions, and the
  before/after result of every view;
* ``objections.jsonl``: "dispute assessment" entries (criterion and reason).
  An objection changes no score and does not train weights.

History files may contain real supplier data. Keep them out of public
repositories (``data/history/`` is git-ignored).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from ..models.config import RiskModelConfig
from ..models.domain import RiskAssessment


class HistoryStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _file(self, view: str) -> Path:
        return self.directory / f"{view}.jsonl"

    def record(
        self,
        assessments: list[RiskAssessment],
        model: RiskModelConfig,
        run_id: str | None = None,
        note: str = "",
        approved_by: str | None = None,
        recorded_at: str | None = None,
    ) -> int:
        """Append a snapshot of ``assessments``. Returns the number of lines written."""
        stamp = recorded_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._file(model.view).open("a", encoding="utf-8") as fh:
            for a in assessments:
                fh.write(json.dumps({
                    "recorded_at": stamp,
                    "run_id": run_id,
                    "view": model.view,
                    "model": f"{model.name}@{model.version}",
                    "note": note,
                    "approved_by": approved_by,
                    "supplier_id": a.supplier_id,
                    "name": a.supplier_name,
                    "material_group": a.material_group,
                    "score": model.to_display(a.overall_score),
                    "risk_class": a.risk_class,
                    "manual_override": a.manual_override,
                    "weights": f"{a.weights_scope}/{a.weights_origin}",
                    "dimensions": {d.dimension: model.to_display(d.score) for d in a.dimension_scores},
                }) + "\n")
        return len(assessments)

    def _append(self, name: str, entry: dict[str, Any]) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    def _read(self, name: str, supplier_id: str | None = None) -> list[dict]:
        path = self.directory / name
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r for r in rows if supplier_id is None or r["supplier_id"] == supplier_id]

    def record_correction(self, request, comparison: dict[str, dict[str, Any]],
                          recorded_at: str | None = None) -> dict[str, Any]:
        """Append a confirmed correction (``tools.corrections``) with its before/after comparison."""
        return self._append("corrections.jsonl", {
            "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "supplier_id": request.supplier_id,
            "status": "applied",
            "changes": [c.model_dump() for c in request.changes],
            "reason": request.reason,
            "entered_by": request.entered_by,
            "identity_verified": False,
            "views": {view: {k: v[k] for k in ("model", "weights", "score", "class", "changed_criteria",
                                               "rules_now_triggered", "rules_no_longer_triggered")}
                      for view, v in comparison.items()},
        })

    def corrections(self, supplier_id: str | None = None) -> list[dict]:
        return self._read("corrections.jsonl", supplier_id)

    def record_objection(self, supplier_id: str, view: str, criterion: str, reason: str,
                         entered_by: str | None = None, context: dict[str, Any] | None = None,
                         recorded_at: str | None = None) -> dict[str, Any]:
        """Append a "dispute assessment" entry. It changes nothing else."""
        if not reason or not reason.strip():
            raise ValueError("a reason for the objection is required")
        return self._append("objections.jsonl", {
            "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "supplier_id": supplier_id,
            "view": view,
            "criterion": criterion,
            "reason": reason.strip(),
            "entered_by": entered_by or None,
            "identity_verified": False,
            "status": "open",
            "context": context or {},
        })

    def objections(self, supplier_id: str | None = None) -> list[dict]:
        return self._read("objections.jsonl", supplier_id)

    def load(self, view: str, supplier_id: str | None = None, material_group: str | None = None) -> list[dict]:
        path = self._file(view)
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if supplier_id:
            rows = [r for r in rows if r["supplier_id"] == supplier_id]
        if material_group:
            rows = [r for r in rows if r["material_group"] == material_group]
        return rows

    def snapshots(self, view: str) -> list[str]:
        return sorted({r["recorded_at"] for r in self.load(view)})

    def group_trend(self, view: str, material_group: str | None = None) -> list[dict[str, Any]]:
        """Per snapshot (and material group): mean score and class counts."""
        buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for r in self.load(view, material_group=material_group):
            buckets[(r["recorded_at"], r["material_group"] or "(none)")].append(r)
        trend = []
        for (stamp, group), rows in sorted(buckets.items()):
            scores = [r["score"] for r in rows if r["score"] is not None]
            trend.append({
                "recorded_at": stamp,
                "material_group": group,
                "suppliers": len(rows),
                "mean_score": round(mean(scores), 1) if scores else None,
                "classes": dict(Counter(r["risk_class"] for r in rows)),
            })
        return trend
