"""External data providers: the slim abstraction.

A provider delivers raw indicators for a supplier, for example a political
stability percentile, an ESG score or an on-time delivery rate. It does not
rate anything. Rating sources (``tools/indicators.py``) turn indicators into
1..5 ratings, so a provider can be swapped without touching the method.

Providers are applied by the Data Collection Agent before scoring
(:func:`enrich`). They fill indicators that are missing in the supplier data,
and they record where each value came from in ``SupplierProfile.indicator_sources``.
Values entered by hand are never overwritten unless ``overwrite=True``.

To add a provider, implement ``name``, ``indicators`` and ``fetch``. See
``docs/data-providers.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..models.domain import SupplierProfile


@dataclass(frozen=True)
class ProviderResult:
    indicators: dict[str, Any]
    source: str  # human-readable origin, e.g. "World Bank WGI 2024"
    as_of: str | None = None  # data vintage, e.g. "2024" or an ISO date
    notes: list[str] = field(default_factory=list)


@runtime_checkable
class ExternalDataProvider(Protocol):
    name: str
    indicators: tuple[str, ...]  # indicator names this provider can deliver

    def fetch(self, profile: SupplierProfile) -> ProviderResult | None:
        """Indicators for one supplier, or None if the provider has nothing for it."""
        ...


def enrich(
    profiles: Iterable[SupplierProfile], providers: Iterable[ExternalDataProvider], overwrite: bool = False
) -> tuple[list[SupplierProfile], list[str]]:
    """Fill indicators from providers. Returns (enriched copies, messages). Input profiles are not modified."""
    providers = list(providers)
    enriched, messages = [], []
    for profile in profiles:
        p = profile.model_copy(deep=True)
        for provider in providers:
            try:
                result = provider.fetch(p)
            except NotImplementedError as exc:
                messages.append(f"{provider.name}: not connected ({exc})")
                continue
            except Exception as exc:  # noqa: BLE001 - a failing feed must not stop the assessment
                messages.append(f"{provider.name}: error for {p.supplier_id}: {exc}")
                continue
            if result is None:
                continue
            for key, value in result.indicators.items():
                if value is None or (key in p.indicators and not overwrite):
                    continue
                p.indicators[key] = value
                p.indicator_sources[key] = f"{result.source}" + (f" ({result.as_of})" if result.as_of else "")
            messages.extend(f"{provider.name}: {note}" for note in result.notes)
        enriched.append(p)
    return enriched, sorted(set(messages))
