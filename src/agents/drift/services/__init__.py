"""Drift Agent Services."""

from src.agents.drift.services.config_fetcher import (
    ConfigFetcher,
    ConfigProvider,
    ResourceType,
    ResourceConfig,
)
from src.agents.drift.services.drift_detector import (
    ConfigDriftDetector,
    DriftType,
    DriftSeverity,
    DriftedField,
    DriftResult,
    AggregatedDriftResult,
)
from src.agents.drift.services.baseline_loader import (
    BaselineLoader,
    BaselineProvider,
    BaselineFile,
)

# Backward compatibility aliases
GitLabClient = BaselineLoader
GitLabProvider = BaselineProvider

__all__ = [
    # Config fetcher
    "ConfigFetcher",
    "ConfigProvider",
    "ResourceType",
    "ResourceConfig",
    # Drift detector
    "ConfigDriftDetector",
    "DriftType",
    "DriftSeverity",
    "DriftedField",
    "DriftResult",
    "AggregatedDriftResult",
    # Baseline loader (new)
    "BaselineLoader",
    "BaselineProvider",
    "BaselineFile",
    # Backward compatibility aliases
    "GitLabClient",
    "GitLabProvider",
]
