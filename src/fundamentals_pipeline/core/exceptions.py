"""Project-specific exception hierarchy.

Defining typed exceptions makes pipeline failures explicit and lets callers
handle recoverable data source issues separately from configuration bugs.
"""


class TradingBotError(Exception):
    """Base application exception for all domain-specific errors."""


class ConfigurationError(TradingBotError):
    """Raised when required configuration is missing or invalid."""


class DataSourceError(TradingBotError):
    """Raised when an upstream data source cannot fulfill a request."""


class SecRequestError(DataSourceError):
    """Raised when a SEC request fails after retry handling.

    Attributes:
        status_code: Last observed HTTP status code, if available.
        attempts: Total request attempts performed before failure.
        url: Endpoint URL that failed.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        attempts: int | None = None,
        url: str | None = None,
    ) -> None:
        """Initialize SEC request error with optional HTTP context.

        Args:
            message: Human-readable failure message.
            status_code: Last HTTP response code observed.
            attempts: Number of attempts made.
            url: SEC endpoint URL.
        """
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts
        self.url = url


class SecRateLimitError(SecRequestError):
    """Raised when SEC returns rate-limit related responses (for example 429)."""


class CrossEraContradictionError(TradingBotError):
    """Raised when measured data contradicts a declared era equivalence.

    Attributes:
        fields: Names of the fields whose declared equivalence failed.
        report_path: Reconciliation report written before the raise, so a
            failing run still leaves its evidence on disk.
    """

    def __init__(
        self,
        message: str,
        *,
        fields: tuple[str, ...] = (),
        report_path: str | None = None,
    ) -> None:
        """Initialize with the contradicting fields and the report location.

        Args:
            message: Human-readable failure message.
            fields: Field names whose declared equivalence was contradicted.
            report_path: Path of the written reconciliation report.
        """
        super().__init__(message)
        self.fields = fields
        self.report_path = report_path
