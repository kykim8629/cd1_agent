"""
BDP Compact Agent Services.

Service modules for multi-account cost drift detection.
"""

from bdp_compact.services.anomaly_detector import (
    CostDriftDetector,
    CostDriftResult,
    Severity,
)
from bdp_compact.services.event_publisher import (
    EventPublisher,
    AlertEvent,
)
from bdp_compact.services.multi_account_provider import (
    AccountConfig,
    BaseMultiAccountProvider,
    MultiAccountCostExplorerProvider,
    ServiceCostData,
    create_provider,
)
from bdp_compact.services.summary_generator import (
    AlertSummary,
    SummaryGenerator,
)

__all__ = [
    "CostDriftDetector",
    "CostDriftResult",
    "Severity",
    "EventPublisher",
    "AlertEvent",
    "AccountConfig",
    "BaseMultiAccountProvider",
    "MultiAccountCostExplorerProvider",
    "ServiceCostData",
    "create_provider",
    "AlertSummary",
    "SummaryGenerator",
]
