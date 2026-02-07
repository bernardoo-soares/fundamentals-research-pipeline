class TradingBotError(Exception):
    """Base application exception."""


class ConfigurationError(TradingBotError):
    """Raised when required configuration is missing or invalid."""


class DataSourceError(TradingBotError):
    """Raised when an upstream data source cannot fulfill a request."""
