"""Versioned, file-based store for approved weight sets.

Each approved (or auto-applied) weight set is written to its own YAML file:

    <directory>/<scope>_v<NNN>.yaml        e.g.  data/weights/global_v002.yaml

Files are never overwritten: every approval creates a new version, so the
history of weights is reviewable in git like any other model change. A run
loads the latest version per scope as its starting weights; older versions can
be loaded explicitly for comparison or rollback.

File content (example)::

    scope: global
    version: 2
    created_at: '2026-10-11T08:15:00+00:00'
    status: approved            # approved | auto_applied
    approved_by: jane.doe
    model: {name: generic-supplier-risk-template, version: 0.1.0}
    origin: calibrated
    calibration: {n_samples: 32, mse_before: 37.77, mse_after: 13.27, improvement: 0.649}
    note: calibrated on 32 expert labels
    factor_weights: {availability: 0.0971, ...}
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..models.config import RiskModelConfig, WeightSet
from ..models.domain import CalibrationReport

_FILE_RE = re.compile(r"^(?P<scope>[a-z0-9_-]+)_v(?P<version>\d{3,})\.yaml$")


def _safe_scope(scope: str) -> str:
    safe = re.sub(r"[^a-z0-9_-]+", "-", scope.lower()).strip("-")
    if not safe:
        raise ValueError(f"cannot derive a file name from scope {scope!r}")
    return safe


class WeightStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def for_view(self, view: str) -> WeightStore:
        """A store in a sub-folder per view, so that risk and performance weights never mix."""
        return WeightStore(self.directory / _safe_scope(view))

    # --- read ------------------------------------------------------------------

    def versions(self, scope: str) -> list[tuple[int, Path]]:
        """All stored versions of a scope, oldest first."""
        if not self.directory.is_dir():
            return []
        safe = _safe_scope(scope)
        found = []
        for path in self.directory.glob(f"{safe}_v*.yaml"):
            m = _FILE_RE.match(path.name)
            if m and m["scope"] == safe:
                found.append((int(m["version"]), path))
        return sorted(found)

    def scopes(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted({m["scope"] for p in self.directory.glob("*.yaml") if (m := _FILE_RE.match(p.name))})

    def read(self, path: str | Path) -> tuple[WeightSet, dict]:
        """Return (weights, full metadata) of one stored file."""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        weights = WeightSet(
            scope=data["scope"],
            origin=data.get("origin", "manual"),
            factor_weights=data["factor_weights"],
            version=data["version"],
            note=data.get("note", ""),
        )
        return weights, data

    def load(self, scope: str, version: int | None = None) -> WeightSet | None:
        """Latest (or a specific) version of a scope; None if nothing is stored."""
        versions = dict(self.versions(scope))
        if not versions:
            return None
        if version is None:
            version = max(versions)
        if version not in versions:
            raise KeyError(f"no version {version} for scope '{scope}'")
        return self.read(versions[version])[0]

    def load_active(self, model: RiskModelConfig) -> tuple[dict[str, WeightSet], list[str]]:
        """Latest weight set per scope that matches the model's factors.

        Returns (weights by scope, warnings). Files whose factors do not match
        the current model (e.g. after criteria changed) are skipped with a warning.
        """
        expected = set(model.factor_keys())
        active: dict[str, WeightSet] = {}
        warnings: list[str] = []
        for scope in self.scopes():
            _, path = self.versions(scope)[-1]
            weights, _ = self.read(path)
            if set(weights.factor_weights) != expected:
                warnings.append(f"stored weights {path.name} ignored: factors do not match the risk model")
                continue
            active[weights.scope] = weights
        return active, warnings

    # --- write -------------------------------------------------------------------

    def save(
        self,
        weights: WeightSet,
        model: RiskModelConfig,
        approved_by: str,
        status: str = "approved",
        report: CalibrationReport | None = None,
    ) -> tuple[Path, int]:
        """Persist ``weights`` as the next version of its scope. Returns (path, version)."""
        self.directory.mkdir(parents=True, exist_ok=True)
        existing = self.versions(weights.scope)
        version = existing[-1][0] + 1 if existing else 1
        path = self.directory / f"{_safe_scope(weights.scope)}_v{version:03d}.yaml"

        data = {
            "scope": weights.scope,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": status,
            "approved_by": approved_by,
            "model": {"name": model.name, "version": model.version},
            "origin": weights.origin,
            "note": weights.note,
        }
        if report is not None:
            data["calibration"] = {
                "n_samples": report.n_samples,
                "mse_before": report.mse_before,
                "mse_after": report.mse_after,
                "improvement": report.improvement,
            }
        data["factor_weights"] = weights.rounded(6)

        # "x" mode: never overwrite an existing version
        with path.open("x", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        return path, version
