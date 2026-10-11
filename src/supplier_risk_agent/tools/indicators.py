"""Translate raw supplier indicators into 1..5 factor ratings.

Each risk factor in the model names a ``source``. A source is a small, pure
function that looks at a :class:`SupplierProfile` and returns a rating plus a
human-readable rationale. Bands and mappings below are *illustrative defaults*
and are meant to be replaced or calibrated for a real supplier base.

To add a new data source, write a function with the ``RatingFn`` signature and
register it with :func:`register_source`.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models.domain import SupplierProfile

RatingResult = tuple[int | None, str]
RatingFn = Callable[[SupplierProfile, str], RatingResult]

_SOURCES: dict[str, RatingFn] = {}


def register_source(name: str) -> Callable[[RatingFn], RatingFn]:
    def decorator(fn: RatingFn) -> RatingFn:
        _SOURCES[name] = fn
        return fn

    return decorator


def available_sources() -> list[str]:
    return sorted(_SOURCES)


def rate_factor(profile: SupplierProfile, factor_key: str, source: str) -> RatingResult:
    """Return the rating for one factor.

    An explicit expert rating for the factor always wins over a derived one,
    so a buyer can override any automatic rating with documented judgement.
    """
    if factor_key in profile.expert_ratings:
        return _validated(profile.expert_ratings[factor_key], "expert rating")
    if source not in _SOURCES:
        return None, f"no rating source registered for '{source}'"
    return _SOURCES[source](profile, factor_key)


def _validated(value: object, origin: str) -> RatingResult:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        return None, f"invalid {origin} {value!r} (expected integer 1..5)"
    return value, origin


def _band(value: float, upper_bounds: list[float]) -> int:
    """Map ``value`` to 1..5 given four ascending exclusive upper bounds."""
    for rating, bound in enumerate(upper_bounds, start=1):
        if value < bound:
            return rating
    return len(upper_bounds) + 1


def _missing(profile: SupplierProfile, key: str) -> bool:
    return profile.indicators.get(key) is None


# --- registered sources ------------------------------------------------------


@register_source("expert_assessment")
def _expert(profile: SupplierProfile, factor_key: str) -> RatingResult:
    # Reached only if no expert rating exists (see rate_factor).
    return None, "expert assessment pending"


@register_source("credit_score")
def _credit(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "credit_score"):
        return None, "no credit score available"
    score = float(profile.indicators["credit_score"])
    # Higher credit score = healthier = lower risk.
    rating = 6 - _band(score, [35, 50, 65, 80])
    return rating, f"credit score {score:g}/100"


@register_source("distress_signals")
def _distress(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "distress_signals"):
        return None, "no distress signal data"
    count = int(profile.indicators["distress_signals"])
    rating = {0: 1, 1: 3, 2: 4}.get(count, 5)
    return rating, f"{count} negative financial signal(s) in observation window"


@register_source("country_risk_index")
def _country(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "country_risk_index"):
        return None, "no country risk index available"
    index = float(profile.indicators["country_risk_index"])
    return _band(index, [20, 40, 60, 80]), f"country risk index {index:g}/100"


@register_source("qualified_sources")
def _sourcing(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "qualified_sources"):
        return None, "number of qualified sources unknown"
    n = int(profile.indicators["qualified_sources"])
    rating = 5 if n <= 1 else 3 if n == 2 else 1
    label = "single source" if n <= 1 else "dual source" if n == 2 else "multi source"
    return rating, f"{label} ({n} qualified source(s))"


TRANSPORT_RATINGS = {"road": 1, "rail": 2, "air": 3, "sea": 4}


@register_source("transport_mode")
def _transport(profile: SupplierProfile, factor_key: str) -> RatingResult:
    mode = profile.indicators.get("transport_mode")
    if mode is None:
        return None, "transport mode unknown"
    rating = TRANSPORT_RATINGS.get(str(mode).lower())
    if rating is None:
        return None, f"unmapped transport mode '{mode}'"
    if profile.indicators.get("intercontinental") and rating < 5:
        rating += 1
        return rating, f"{mode} freight, intercontinental route"
    return rating, f"{mode} freight"


@register_source("esg_score")
def _esg(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "esg_score"):
        return None, "no ESG score available"
    score = float(profile.indicators["esg_score"])
    return 6 - _band(score, [25, 45, 60, 75]), f"ESG score {score:g}/100"


@register_source("on_time_rate")
def _on_time(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "on_time_rate"):
        return None, "no on-time delivery rate available"
    rate = float(profile.indicators["on_time_rate"])
    # higher on-time rate = better; bands are illustrative
    rating = 1 if rate >= 98 else 2 if rate >= 95 else 3 if rate >= 90 else 4 if rate >= 85 else 5
    return rating, f"on-time delivery {rate:g} %"


@register_source("quality_ppm")
def _ppm(profile: SupplierProfile, factor_key: str) -> RatingResult:
    if _missing(profile, "quality_ppm"):
        return None, "no PPM figure available"
    ppm = float(profile.indicators["quality_ppm"])
    return _band(ppm, [50, 200, 500, 1000]), f"{ppm:g} PPM"


COMPLIANCE_RATINGS = {
    "compliant": 1,
    "minor_findings": 2,
    "open_findings": 3,
    "major_findings": 4,
    "critical_findings": 5,
}


@register_source("compliance_status")
def _compliance(profile: SupplierProfile, factor_key: str) -> RatingResult:
    status = profile.indicators.get("compliance_status")
    if status is None:
        return None, "compliance status not assessed"
    rating = COMPLIANCE_RATINGS.get(str(status))
    if rating is None:
        return None, f"unmapped compliance status '{status}'"
    return rating, f"compliance status: {status}"
