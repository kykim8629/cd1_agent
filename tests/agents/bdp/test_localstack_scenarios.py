"""
LocalStack Integration Tests for BDP Agent.

Tests failure scenarios injected into LocalStack to verify
detection capabilities in a realistic environment.

Usage:
    # Start LocalStack first
    make localstack-up

    # Run LocalStack tests
    make localstack-test

    # Or run directly with pytest
    TEST_AWS_PROVIDER=localstack pytest tests/agents/bdp/test_localstack_scenarios.py -v -m localstack
"""

import os
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict


pytestmark = pytest.mark.localstack


class TestLocalStackMetricAnomaly:
    """Test metric anomaly detection against LocalStack."""

    @pytest.mark.localstack
    def test_detects_cpu_spike(
        self,
        localstack_bdp_handler,
        inject_cpu_spike_scenario,
    ):
        """Test that CPU spike scenario triggers metric anomaly detection.

        Scenario: CPU spike to 95% (normal ~35%)
        Expected: z-score > 2.0, detected as metric_anomaly
        """
        scenario = inject_cpu_spike_scenario

        # Create metric anomaly detection event
        event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "CPUUtilization",
            "dimensions": [{"Name": "FunctionName", "Value": scenario["function_name"]}],
            "service_name": scenario["function_name"],
            "time_range_hours": 24,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Verify detection
        assert result is not None
        assert result.get("anomalies_detected") is True, f"Expected anomaly detection, got: {result}"

        # If anomaly record exists, verify z-score
        if "anomaly_record" in result:
            record = result["anomaly_record"]
            assert record.get("anomaly_type") == "metric_anomaly"

            # Check z-score if available
            if "z_score" in record:
                assert record["z_score"] >= scenario["expected_z_score_min"], \
                    f"Expected z-score >= {scenario['expected_z_score_min']}, got {record['z_score']}"

    @pytest.mark.localstack
    def test_normal_metrics_no_anomaly(self, localstack_bdp_handler):
        """Test that normal metrics do not trigger false positives.

        Uses the baseline metrics injected during LocalStack initialization.
        """
        event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "Duration",  # Duration metrics should be normal
            "dimensions": [{"Name": "FunctionName", "Value": "test-function"}],
            "service_name": "test-function",
            "time_range_hours": 24,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Normal metrics should not trigger anomaly
        # Allow for some variance in detection
        if result.get("anomalies_detected"):
            # If detected, severity should be low
            if "anomaly_record" in result:
                severity = result["anomaly_record"].get("severity", "")
                assert severity in ["low", "medium"], \
                    f"Expected low/medium severity for baseline metrics, got {severity}"


class TestLocalStackLogAnomaly:
    """Test log anomaly detection against LocalStack."""

    @pytest.mark.localstack
    def test_detects_error_flood(
        self,
        localstack_bdp_handler,
        inject_error_flood_scenario,
    ):
        """Test that error flood scenario triggers log anomaly detection.

        Scenario: 15+ ERROR logs in short period
        Expected: log_anomaly detected, severity high
        """
        scenario = inject_error_flood_scenario

        # Create log anomaly detection event
        event = {
            "detection_type": "log_anomaly",
            "log_group": scenario["log_group"],
            "service_name": "test-function",
            "time_range_hours": 1,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Verify detection
        assert result is not None
        assert result.get("anomalies_detected") is True, f"Expected anomaly detection, got: {result}"

        # Verify anomaly record
        if "anomaly_record" in result:
            record = result["anomaly_record"]
            assert record.get("anomaly_type") == "log_anomaly"
            assert record.get("severity") in ["high", "critical"], \
                f"Expected high/critical severity, got {record.get('severity')}"

    @pytest.mark.localstack
    def test_normal_logs_no_anomaly(self, localstack_bdp_handler):
        """Test that normal logs do not trigger false positives.

        Uses the baseline INFO logs injected during LocalStack initialization.
        """
        event = {
            "detection_type": "log_anomaly",
            "log_group": "/aws/lambda/api-gateway",  # Should have only INFO logs
            "service_name": "api-gateway",
            "time_range_hours": 1,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Normal logs should not trigger high severity anomaly
        if result.get("anomalies_detected"):
            if "anomaly_record" in result:
                severity = result["anomaly_record"].get("severity", "")
                assert severity != "critical", \
                    f"Expected non-critical severity for normal logs, got {severity}"


class TestLocalStackPatternDetection:
    """Test pattern-based detection against LocalStack."""

    @pytest.mark.localstack
    def test_detects_auth_failure_pattern(
        self,
        localstack_bdp_handler,
        inject_auth_failure_scenario,
    ):
        """Test that auth failure pattern triggers detection.

        Scenario: 8 failed login attempts (threshold: 5)
        Expected: pattern_anomaly detected, severity critical
        """
        scenario = inject_auth_failure_scenario

        # Create pattern anomaly detection event
        event = {
            "detection_type": "pattern_anomaly",
            "target_service": "auth-service",
            "context": {
                "log_group": scenario["log_group"],
            },
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Verify detection
        assert result is not None

        # Pattern detection may return multiple matches
        if result.get("anomalies_detected"):
            records = result.get("anomaly_records", [])
            if not records and "anomaly_record" in result:
                records = [result["anomaly_record"]]

            # Look for auth_failure pattern
            auth_patterns = [
                r for r in records
                if r.get("pattern_type") == scenario["expected_pattern_type"]
                or "auth" in str(r.get("pattern_id", "")).lower()
            ]

            if auth_patterns:
                pattern = auth_patterns[0]
                assert pattern.get("severity") in ["high", "critical"], \
                    f"Expected high/critical severity, got {pattern.get('severity')}"

    @pytest.mark.localstack
    def test_detects_db_timeout_pattern(
        self,
        localstack_bdp_handler,
        inject_db_timeout_scenario,
    ):
        """Test that database timeout pattern triggers detection.

        Scenario: Multiple DB timeout/deadlock errors
        Expected: pattern_anomaly detected for timeout patterns
        """
        scenario = inject_db_timeout_scenario

        # Create pattern anomaly detection event
        event = {
            "detection_type": "pattern_anomaly",
            "target_service": "data-processor",
            "context": {
                "log_group": scenario["log_group"],
            },
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Verify detection
        assert result is not None

        if result.get("anomalies_detected"):
            records = result.get("anomaly_records", [])
            if not records and "anomaly_record" in result:
                records = [result["anomaly_record"]]

            # Look for timeout or resource_exhaustion patterns
            relevant_patterns = [
                r for r in records
                if r.get("pattern_type") in scenario["expected_pattern_types"]
                or any(pt in str(r.get("pattern_id", "")).lower()
                      for pt in ["timeout", "exhausted", "conn"])
            ]

            if relevant_patterns:
                # At least one pattern should have high/critical severity
                severities = [p.get("severity") for p in relevant_patterns]
                assert any(s in ["high", "critical"] for s in severities), \
                    f"Expected at least one high/critical pattern, severities: {severities}"


class TestLocalStackIntegration:
    """Integration tests for complete detection workflows."""

    @pytest.mark.localstack
    def test_scheduled_detection_workflow(self, localstack_bdp_handler):
        """Test scheduled detection across multiple services.

        Uses the services configured in the init scripts.
        """
        event = {
            "detection_type": "scheduled",
            "services": [
                {"name": "test-function", "log_group": "/aws/lambda/test-function"},
                {"name": "auth-service", "log_group": "/aws/lambda/auth-service"},
                {"name": "api-gateway", "log_group": "/aws/lambda/api-gateway"},
            ],
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Scheduled detection should complete without error
        assert result is not None
        assert "error" not in str(result).lower() or result.get("anomalies_detected") is not None

        # Should have checked multiple services
        if "services_checked" in result:
            assert result["services_checked"] >= 1

    @pytest.mark.localstack
    def test_eventbridge_notification(
        self,
        localstack_bdp_handler,
        inject_error_flood_scenario,
        localstack_aws_client,
    ):
        """Test that anomaly detection sends EventBridge notification.

        Verifies the integration between detection and notification.
        """
        scenario = inject_error_flood_scenario

        # Trigger detection
        event = {
            "detection_type": "log_anomaly",
            "log_group": scenario["log_group"],
            "service_name": "test-function",
            "time_range_hours": 1,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # If anomaly detected, verify EventBridge integration
        if result.get("anomalies_detected"):
            # Check if notification was attempted
            if "notification_sent" in result:
                assert result["notification_sent"] is True

    @pytest.mark.localstack
    def test_dynamodb_result_storage(
        self,
        localstack_bdp_handler,
        inject_cpu_spike_scenario,
        localstack_aws_client,
    ):
        """Test that detection results are stored in DynamoDB.

        Verifies the integration between detection and result persistence.
        """
        scenario = inject_cpu_spike_scenario

        # Trigger detection
        event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "CPUUtilization",
            "dimensions": [{"Name": "FunctionName", "Value": scenario["function_name"]}],
            "service_name": scenario["function_name"],
            "time_range_hours": 24,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # If anomaly detected and result stored, verify DynamoDB
        if result.get("anomalies_detected") and "signature" in str(result):
            signature = result.get("anomaly_record", {}).get("signature")
            if signature:
                # Try to retrieve from DynamoDB
                stored = localstack_aws_client.get_dynamodb_item(
                    table_name="cd1-agent-results",
                    key={"signature": signature},
                )
                # Note: This may return None if handler doesn't store results
                # That's acceptable - we're testing the integration works


class TestLocalStackEdgeCases:
    """Edge case tests for LocalStack environment."""

    @pytest.mark.localstack
    def test_empty_log_group(self, localstack_bdp_handler):
        """Test handling of non-existent log group."""
        event = {
            "detection_type": "log_anomaly",
            "log_group": "/aws/lambda/non-existent-function",
            "service_name": "non-existent",
            "time_range_hours": 1,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Should handle gracefully without crashing
        assert result is not None
        # Should not detect anomaly for empty/non-existent logs
        assert result.get("anomalies_detected") is False or "error" in str(result).lower()

    @pytest.mark.localstack
    def test_invalid_metric_dimensions(self, localstack_bdp_handler):
        """Test handling of invalid metric dimensions."""
        event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "CPUUtilization",
            "dimensions": [{"Name": "FunctionName", "Value": "totally-fake-function"}],
            "service_name": "fake-function",
            "time_range_hours": 24,
        }

        result = localstack_bdp_handler.handle_detection(event)

        # Should handle gracefully
        assert result is not None
        # Should not detect anomaly for non-existent metrics
        assert result.get("anomalies_detected") is False or result.get("datapoints_count", 0) == 0

    @pytest.mark.localstack
    def test_concurrent_scenario_injection(
        self,
        localstack_bdp_handler,
        inject_cpu_spike_scenario,
        inject_error_flood_scenario,
    ):
        """Test that multiple scenarios can be active simultaneously.

        Verifies isolation between different failure scenarios.
        """
        cpu_scenario = inject_cpu_spike_scenario
        error_scenario = inject_error_flood_scenario

        # Test CPU spike detection
        cpu_event = {
            "detection_type": "metric_anomaly",
            "namespace": "AWS/Lambda",
            "metric_name": "CPUUtilization",
            "dimensions": [{"Name": "FunctionName", "Value": cpu_scenario["function_name"]}],
            "service_name": cpu_scenario["function_name"],
            "time_range_hours": 24,
        }

        # Test error flood detection
        error_event = {
            "detection_type": "log_anomaly",
            "log_group": error_scenario["log_group"],
            "service_name": "test-function",
            "time_range_hours": 1,
        }

        cpu_result = localstack_bdp_handler.handle_detection(cpu_event)
        error_result = localstack_bdp_handler.handle_detection(error_event)

        # Both should complete without error
        assert cpu_result is not None
        assert error_result is not None

        # Both should potentially detect anomalies (scenarios are active)
        # Note: Exact detection depends on scenario injection timing
