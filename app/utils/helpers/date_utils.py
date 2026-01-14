"""Date helper placeholders."""


def parse_receipt_date(value):
    """Parse receipt dates across varying formats.

    TODO: Handle Japanese locale, handwritten dates, and fallback heuristics.
    """
    return None


def normalize_month_key(dt):
    """Return a canonical YYYY-MM key for dedupe + ledgers.

    TODO: Wire to timezone-aware conversions.
    """
    return None
