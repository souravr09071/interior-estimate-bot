"""
Mock pricing config for the POC.
Rates are illustrative ₹/sq ft figures for full interior fit-out
(kitchen, wardrobes, TV unit, vanity, shoe rack, false ceiling).
Tune these freely — they are not based on a real vendor quote.
"""

STYLE_TIERS = {
    "functional": {
        "label": "Functional & Beautiful",
        "tagline": "Smart, Simple, Functional, Great value.",
        "detail": "Modern laminates, reliable fittings, functional storage, best for rental homes and small homes",
        "rate_per_sqft": 950,
    },
    "elegant": {
        "label": "Elegant Everyday Living",
        "tagline": "Premium, Elegant, Balanced, Timeless",
        "detail": "Premium laminates, soft-close hardware, designer finishes, most popular choice",
        "rate_per_sqft": 1400,
    },
    "refined": {
        "label": "Refined Designer Home",
        "tagline": "Sophisticated, Warm, Rich detailing",
        "detail": "Premium veneers & acrylics, imported hardware, designer lighting, custom detailing",
        "rate_per_sqft": 2100,
    },
    "signature": {
        "label": "One-of-a-Kind Dream Home",
        "tagline": "Signature, One-of-a-kind, Completely bespoke.",
        "detail": "Fully customized, luxury materials, architect-designed detailing, unlimited personalization",
        "rate_per_sqft": 3200,
    },
}

BUDGET_RANGES = {
    "under_10l": {"label": "Under ₹10L", "min": 0, "max": 1_000_000},
    "10l_15l": {"label": "₹10L–15L", "min": 1_000_000, "max": 1_500_000},
    "15l_20l": {"label": "₹15L–20L", "min": 1_500_000, "max": 2_000_000},
    "20l_30l": {"label": "₹20L–30L", "min": 2_000_000, "max": 3_000_000},
    "more_30l": {"label": "More than ₹30L", "min": 3_000_000, "max": None},
    "not_sure": {"label": "Not sure yet", "min": None, "max": None},
}

DEFAULT_SCOPE_ITEMS = [
    "Kitchen",
    "Wardrobes",
    "TV Unit",
    "Vanity",
    "Shoe Rack",
    "False Ceiling",
]


def estimate_cost(area_sqft: float, style_key: str) -> dict:
    """Given an estimated area and a chosen style tier, return a mocked
    estimate dict matching the shape used in the conversation flow."""
    tier = STYLE_TIERS[style_key]
    total = round(area_sqft * tier["rate_per_sqft"])
    return {
        "scope": DEFAULT_SCOPE_ITEMS,
        "estimated_investment": total,
        "estimated_investment_lakhs": round(total / 100000, 1),
        "confidence": 91,  # mocked, for display purposes only in the POC
    }


def compare_to_budget(estimate_amount: int, budget_key: str) -> str:
    """Returns 'over', 'under', 'match', or 'unknown' (for 'not_sure')."""
    budget = BUDGET_RANGES[budget_key]
    if budget["min"] is None and budget["max"] is None:
        return "unknown"

    budget_max = budget["max"] if budget["max"] is not None else budget["min"] * 1.5
    budget_min = budget["min"]

    # simple tolerance band around the range to decide "match" vs over/under
    if estimate_amount > budget_max * 1.05:
        return "over"
    elif estimate_amount < budget_min * 0.95:
        return "under"
    else:
        return "match"