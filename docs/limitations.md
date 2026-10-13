# Limitations and validation boundaries

[Back to the product overview](../README.md)

- **Template, not a validated model.** The bundled criteria, weights and thresholds are
  illustrative. Adapt them to your categories and calibrate them on your own supplier base before
  using results for decisions.
- **Synthetic evidence only.** The calibration experiments in the paper use synthetic expert labels
  from constructed expert policies. There is no field validation with real category managers yet.
- **No live data connections.** External risk signals (sanctions, insolvencies, events) and live
  APIs are not implemented; indicators come from files.
- **Single-user prototype.** Review state lives in memory per session; there are no roles,
  authentication or multi-user workflows.
- **Explain & correct is not validated in practice.** Its usefulness for category managers, the
  quality of the explanations and the accuracy of corrections have not been evaluated, and no
  reduction of false alarms is claimed. The LLM explanation sends data to an external provider when
  you trigger it, and its text can contain errors.
- **Corrections are single-user.** Names are typed in and not verified; there are no roles or
  approval of corrections by a second person. A CSV import or **Try the demo** replaces the whole data
  set and is not recorded as a correction.

See also [LLM validation limits](llm-explanation.md), the
[benchmark caveats](../research/comparison-matrix.md#known-weaknesses-of-this-comparison),
and [native Streamlit localisation limits](professional-ui.md#grenzen-nativer-streamlit-elemente).
