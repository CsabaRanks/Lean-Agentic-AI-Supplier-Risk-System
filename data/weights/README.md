# Weight store

Approved or auto-applied weight sets are written here when a run uses
`--weights-dir data/weights` (CLI) or `WeightStore("data/weights")` (Python).

- One file per version and scope: `global_v001.yaml`, `global_v002.yaml`, `plastics_v001.yaml`, …
- Files are never overwritten. Each approval creates a new version with a timestamp,
  approver, model version and calibration metrics (MSE before/after).
- A run starts from the **latest** version per scope; older versions can be loaded for
  comparison or rollback (`WeightStore.load(scope, version=1)`).
- Files whose factors do not match the current risk model are ignored with a warning.

In this public repository the generated subfolders (`risk/`, `performance/`) are git-ignored, so
demo runs do not end up in commits. In a private fork, remove the `data/weights/*/` line from
`.gitignore` and commit these files like any other model change. That gives you a reviewable history
of who changed which weights, when and why. Weights calibrated on real supplier data may be
confidential: keep them out of public repositories.
