"""
Drift Detection Handler for AWS Configuration Drift Detection Lambda.

Entry point for Drift Agent - detects configuration drifts between
GitLab baselines and current AWS resource configurations.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.handlers.base_handler import BaseHandler
from src.services.gitlab_client import GitLabClient
from src.services.config_fetcher import ConfigFetcher, ResourceType
from src.services.config_drift_detector import (
    ConfigDriftDetector,
    DriftResult,
    DriftSeverity,
    AggregatedDriftResult,
)
from src.services.aws_client import AWSClient, AWSProvider


# Resource mapping from string to ResourceType
RESOURCE_TYPE_MAP = {
    "EKS": ResourceType.EKS,
    "MSK": ResourceType.MSK,
    "S3": ResourceType.S3,
    "EMR": ResourceType.EMR,
    "MWAA": ResourceType.MWAA,
}

# Default resources to check per type
DEFAULT_RESOURCES = {
    "EKS": ["production-eks"],
    "MSK": ["production-kafka"],
    "S3": ["company-data-lake-prod"],
    "EMR": ["j-XXXXX"],
    "MWAA": ["bdp-airflow-prod"],
}


class DriftDetectionHandler(BaseHandler):
    """
    Lambda handler for AWS configuration drift detection.

    Compares current AWS resource configurations against GitLab baselines
    to detect and classify configuration drifts:
    - EKS: Cluster and node group configurations
    - MSK: Kafka cluster configurations
    - S3: Bucket security and lifecycle configurations
    - EMR: Cluster and instance group configurations
    - MWAA: Airflow environment configurations

    Triggers analysis workflow when critical/high severity drifts are detected.
    """

    def __init__(self):
        super().__init__("DriftDetectionHandler")
        self._init_clients()

    def _init_clients(self) -> None:
        """Initialize service clients based on configuration."""
        aws_provider = AWSProvider(self.config["aws_provider"])
        self.aws_client = AWSClient(provider=aws_provider)

        # GitLab and Config clients auto-detect mock mode
        self.gitlab_client = GitLabClient()
        self.config_fetcher = ConfigFetcher()
        self.drift_detector = ConfigDriftDetector()

    def _validate_input(self, event: Dict[str, Any]) -> Optional[str]:
        """Validate drift detection event."""
        body = self._parse_body(event)

        # Validate resource_types if provided
        resource_types = body.get("resource_types", event.get("resource_types", []))
        if resource_types:
            for rt in resource_types:
                if rt.upper() not in RESOURCE_TYPE_MAP:
                    return f"Invalid resource_type: {rt}. Must be one of: {list(RESOURCE_TYPE_MAP.keys())}"

        # Validate severity_threshold if provided
        severity_threshold = body.get(
            "severity_threshold",
            event.get("severity_threshold", "LOW"),
        )
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        if severity_threshold.upper() not in valid_severities:
            return f"Invalid severity_threshold: {severity_threshold}. Must be one of: {valid_severities}"

        return None

    def process(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """Process drift detection request."""
        body = self._parse_body(event)

        # Get configuration from event or body
        resource_types = body.get("resource_types", event.get("resource_types", []))
        resources = body.get("resources", event.get("resources", {}))
        severity_threshold = body.get(
            "severity_threshold",
            event.get("severity_threshold", "LOW"),
        ).upper()
        baseline_ref = body.get("baseline_ref", event.get("baseline_ref"))

        # Use defaults if no resources specified
        if not resource_types:
            resource_types = list(RESOURCE_TYPE_MAP.keys())

        self.logger.info(
            f"Processing drift detection for resource types: {resource_types}"
        )

        # Run drift detection
        result = self._run_drift_detection(
            resource_types=resource_types,
            resources=resources,
            baseline_ref=baseline_ref,
            severity_threshold=severity_threshold,
        )

        self.logger.info(
            f"Detection complete: {result.total_drift_count} drifts found "
            f"(critical: {result.severity_summary.get('CRITICAL', 0)}, "
            f"high: {result.severity_summary.get('HIGH', 0)})"
        )

        # Store results
        self._store_drift_results(result)

        # Trigger analysis for critical/high drifts
        if (
            result.severity_summary.get("CRITICAL", 0) > 0 or
            result.severity_summary.get("HIGH", 0) > 0
        ):
            self._trigger_analysis(result)

        return result.to_dict()

    def _run_drift_detection(
        self,
        resource_types: List[str],
        resources: Dict[str, List[str]],
        baseline_ref: Optional[str],
        severity_threshold: str,
    ) -> AggregatedDriftResult:
        """Run drift detection across all specified resources."""
        drifts: List[DriftResult] = []
        resources_analyzed = 0

        # Get baseline commit info
        try:
            commit_info = self.gitlab_client.get_commit_info(ref=baseline_ref)
            baseline_info = {
                "ref": baseline_ref or self.gitlab_client.baseline_ref,
                "commit_sha": commit_info.get("sha", ""),
            }
        except Exception as e:
            self.logger.warning(f"Failed to get baseline commit info: {e}")
            baseline_info = {
                "ref": baseline_ref or self.gitlab_client.baseline_ref,
                "commit_sha": "unknown",
            }

        for resource_type in resource_types:
            rt_upper = resource_type.upper()

            # Get resources to check
            resource_list = resources.get(rt_upper, DEFAULT_RESOURCES.get(rt_upper, []))

            for resource_id in resource_list:
                try:
                    drift_result = self._check_resource_drift(
                        resource_type=rt_upper,
                        resource_id=resource_id,
                        baseline_ref=baseline_ref,
                        baseline_version=baseline_info.get("commit_sha", ""),
                    )

                    # Apply severity filter
                    if self._meets_severity_threshold(drift_result, severity_threshold):
                        drifts.append(drift_result)

                    resources_analyzed += 1

                except Exception as e:
                    self.logger.error(
                        f"Failed to check drift for {rt_upper}:{resource_id}: {e}"
                    )
                    resources_analyzed += 1

        return AggregatedDriftResult(
            drifts=drifts,
            resources_analyzed=resources_analyzed,
            detection_timestamp=datetime.utcnow().isoformat(),
            baseline_info=baseline_info,
        )

    def _check_resource_drift(
        self,
        resource_type: str,
        resource_id: str,
        baseline_ref: Optional[str],
        baseline_version: str,
    ) -> DriftResult:
        """Check drift for a single resource."""
        self.logger.debug(f"Checking drift for {resource_type}:{resource_id}")

        # Get baseline from GitLab
        baseline_file = self.gitlab_client.get_resource_baseline(
            resource_type=resource_type.lower(),
            resource_name=resource_id,
            ref=baseline_ref,
        )

        # Get current config from AWS
        current_config = self.config_fetcher.get_config(
            resource_type=RESOURCE_TYPE_MAP[resource_type],
            resource_id=resource_id,
        )

        # Detect drifts
        return self.drift_detector.detect(
            baseline=baseline_file.content,
            current=current_config.config,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_arn=current_config.resource_arn,
            baseline_version=baseline_version,
        )

    def _meets_severity_threshold(
        self,
        drift_result: DriftResult,
        threshold: str,
    ) -> bool:
        """Check if drift result meets severity threshold."""
        if not drift_result.has_drift:
            return True  # Include resources without drifts

        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        threshold_idx = severity_order.index(threshold)

        # Check if any drift meets the threshold
        for field in drift_result.drifted_fields:
            field_idx = severity_order.index(field.severity.value)
            if field_idx <= threshold_idx:
                return True

        return False

    def _store_drift_results(self, result: AggregatedDriftResult) -> None:
        """Store drift detection results in DynamoDB."""
        try:
            # Store summary record
            date_str = result.detection_timestamp[:10]
            self.aws_client.put_dynamodb_item(
                table_name=self.config["dynamodb_table"],
                item={
                    "pk": f"DRIFT#{date_str}",
                    "sk": f"DETECTION#{result.detection_timestamp}",
                    "type": "drift_detection",
                    "drifts_detected": result.has_drifts,
                    "total_drift_count": result.total_drift_count,
                    "resources_analyzed": result.resources_analyzed,
                    "severity_summary": json.dumps(result.severity_summary),
                    "baseline_info": json.dumps(result.baseline_info),
                    "timestamp": result.detection_timestamp,
                },
            )

            # Store individual drift records for tracking
            for drift in result.drifts:
                if not drift.has_drift:
                    continue

                self.aws_client.put_dynamodb_item(
                    table_name=self.config["dynamodb_table"],
                    item={
                        "pk": f"DRIFT#{drift.resource_type}#{drift.resource_id}",
                        "sk": f"DRIFT#{drift.detection_timestamp}",
                        "type": "resource_drift",
                        "resource_type": drift.resource_type,
                        "resource_id": drift.resource_id,
                        "resource_arn": drift.resource_arn,
                        "severity": drift.max_severity.value if drift.max_severity else None,
                        "drift_count": len(drift.drifted_fields),
                        "baseline_version": drift.baseline_version,
                        "drifted_fields": json.dumps([
                            f.to_dict() for f in drift.drifted_fields
                        ]),
                        "timestamp": drift.detection_timestamp,
                    },
                )

            self.logger.info(
                f"Stored drift detection results: {result.total_drift_count} drifts"
            )

        except Exception as e:
            self.logger.error(f"Failed to store drift detection results: {e}")

    def _trigger_analysis(self, result: AggregatedDriftResult) -> None:
        """Publish drift event to EventBridge for downstream analysis."""
        try:
            # Create aggregated event data
            event_data = {
                "signature": f"drift_{result.detection_timestamp[:10]}",
                "anomaly_type": "config_drift",
                "service_name": "drift-agent",
                "agent": "drift",
                "first_seen": result.detection_timestamp,
                "last_seen": result.detection_timestamp,
                "severity": self._get_highest_severity(result),
                "summary": (
                    f"Configuration drift detected: {result.total_drift_count} drifts "
                    f"across {result.resources_analyzed} resources"
                ),
                "drift_details": result.drift_details[:10],  # Limit size
                "severity_summary": result.severity_summary,
                "baseline_info": result.baseline_info,
            }

            self.aws_client.put_eventbridge_event(
                event_bus=self.config["event_bus"],
                source="bdp-agent.drift",
                detail_type="Configuration Drift Detected",
                detail=event_data,
            )

            self.logger.info(
                f"Analysis triggered for drift detection: {event_data['signature']}"
            )

        except Exception as e:
            self.logger.error(f"Failed to trigger drift analysis: {e}")

    def _get_highest_severity(self, result: AggregatedDriftResult) -> str:
        """Get the highest severity level from detection result."""
        summary = result.severity_summary
        if summary.get("CRITICAL", 0) > 0:
            return "critical"
        elif summary.get("HIGH", 0) > 0:
            return "high"
        elif summary.get("MEDIUM", 0) > 0:
            return "medium"
        return "low"


# Lambda entry point
handler_instance = DriftDetectionHandler()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda function entry point."""
    return handler_instance.handle(event, context)
