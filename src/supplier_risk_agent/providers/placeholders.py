"""Placeholders for API integrations that are planned but not built.

Each class documents which indicators it would deliver. Calling ``fetch`` raises
``NotImplementedError``; :func:`enrich` reports this as "not connected" and
scoring continues with the data available.

Until an integration exists, export the data and use ``CsvIndicatorProvider``.
Vendors are mentioned only as generic examples of a kind of system.
"""

from __future__ import annotations

from ..models.domain import SupplierProfile
from .base import ProviderResult


class _ApiPlaceholder:
    name = "placeholder"
    indicators: tuple[str, ...] = ()
    how_to = "export the data and use CsvIndicatorProvider"

    def fetch(self, profile: SupplierProfile) -> ProviderResult | None:
        raise NotImplementedError(f"API integration not built yet; {self.how_to}")


class EsgPlatformProvider(_ApiPlaceholder):
    """ESG / sustainability rating platforms (supplier ESG scores, questionnaire status)."""

    name = "esg_platform"
    indicators = ("esg_score", "compliance_status")


class ErpDeliveryProvider(_ApiPlaceholder):
    """ERP systems (e.g. SAP) for delivery performance: on-time rate and PPM per supplier."""

    name = "erp_delivery_performance"
    indicators = ("on_time_rate", "quality_ppm")


class CreditAgencyProvider(_ApiPlaceholder):
    """Credit agencies: credit score and insolvency / distress signals."""

    name = "credit_agency"
    indicators = ("credit_score", "distress_signals")


PLANNED_PROVIDERS = [EsgPlatformProvider, ErpDeliveryProvider, CreditAgencyProvider]
