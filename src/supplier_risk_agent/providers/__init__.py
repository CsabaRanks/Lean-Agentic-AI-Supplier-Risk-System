"""External data providers (see ``docs/data-providers.md``)."""

from .base import ExternalDataProvider, ProviderResult, enrich
from .csv_provider import CsvIndicatorProvider
from .placeholders import (
    PLANNED_PROVIDERS,
    CreditAgencyProvider,
    ErpDeliveryProvider,
    EsgPlatformProvider,
)
from .world_bank import WorldBankWgiProvider

__all__ = [
    "PLANNED_PROVIDERS",
    "CreditAgencyProvider",
    "CsvIndicatorProvider",
    "ErpDeliveryProvider",
    "EsgPlatformProvider",
    "ExternalDataProvider",
    "ProviderResult",
    "WorldBankWgiProvider",
    "enrich",
]
