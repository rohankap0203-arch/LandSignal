from __future__ import annotations

from landsignal.services.url_intelligence.adapters.generic import GenericListingAdapter
from landsignal.services.url_intelligence.adapters.known import KNOWN_ADAPTERS


def select_adapter(url: str, domain: str):
    for adapter in KNOWN_ADAPTERS:
        if adapter.can_handle(url, domain):
            return adapter
    return GenericListingAdapter()
