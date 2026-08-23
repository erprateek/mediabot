"""
src/services/errors.py
Shared exception types for external API integrations.
"""


class ExternalAPIError(Exception):
    """Raised when an external API is unreachable or keeps failing after retries.

    Callers use this to distinguish "the API is down" (skip/leave data as-is)
    from legitimate empty results (e.g. title not found → no platforms).
    """
