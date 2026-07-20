# -*- coding: utf-8 -*-

TIER_CART = "cart"
TIER_ADS = "ads"
TIER_CATALOG = "catalog"

ALL_TIERS = (TIER_CART, TIER_ADS, TIER_CATALOG)


def resolve_tiers(selected):
    """Normalize tier CLI args; default to all when empty."""
    if not selected:
        return list(ALL_TIERS)

    resolved = []
    seen = set()
    for raw in selected:
        for part in str(raw).replace(",", " ").split():
            key = part.strip().lower()
            if key not in ALL_TIERS:
                raise ValueError(
                    "Unknown tier {!r}. Choose from: {}".format(
                        part, ", ".join(ALL_TIERS)
                    )
                )
            if key not in seen:
                seen.add(key)
                resolved.append(key)
    if not resolved:
        raise ValueError(
            "No tiers selected. Choose from: {}".format(", ".join(ALL_TIERS))
        )
    return [tier for tier in ALL_TIERS if tier in resolved]
