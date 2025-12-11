"""
Unit Tests for Cost Agent Services.

Tests for Cost Explorer client and Cost Anomaly Detector.
"""

import pytest
from datetime import datetime, timedelta

from src.agents.cost.services.cost_explorer_client import CostExplorerClient
from src.agents.cost.services.anomaly_detector import CostAnomalyDetector, DetectionMethod


class TestCostAnomalyDetector:
    """Test suite for cost anomaly detector."""

    def test_detector_creation(self):
        """Test CostAnomalyDetector creation."""
        detector = CostAnomalyDetector(sensitivity=0.7)

        assert detector.sensitivity == 0.7

    def test_analyze_service_normal(self):
        """Test analyzing service with normal costs."""
        detector = CostAnomalyDetector()

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=105.0,
            historical_costs=[100.0, 102.0, 98.0, 105.0, 101.0, 103.0, 100.0],
        )

        assert result.is_anomaly is False
        assert result.service_name == "Lambda"

    def test_analyze_service_anomaly(self):
        """Test analyzing service with anomalous costs."""
        detector = CostAnomalyDetector()

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=250.0,  # 2.5x increase
            historical_costs=[100.0, 102.0, 98.0, 105.0, 101.0, 103.0, 100.0],
        )

        assert result.is_anomaly is True
        assert result.confidence_score > 0.5

    def test_analyze_service_insufficient_data(self):
        """Test analyzing service with insufficient data."""
        detector = CostAnomalyDetector(min_data_points=7)

        result = detector.analyze_service(
            service_name="Lambda",
            current_cost=150.0,
            historical_costs=[100.0, 102.0],  # Only 2 points
        )

        assert result.is_anomaly is False
        assert "insufficient" in result.analysis.lower()

    def test_analyze_batch(self, sample_cost_data):
        """Test batch analysis."""
        detector = CostAnomalyDetector()

        results = detector.analyze_batch(sample_cost_data)

        assert len(results) == 2
        # Results should be sorted by confidence

    def test_detection_methods(self):
        """Test individual detection methods."""
        detector = CostAnomalyDetector()

        # Ratio method
        ratio_result = detector._detect_ratio_anomaly(
            current=200.0,
            historical=[100.0, 100.0, 100.0, 100.0, 100.0],
        )

        assert ratio_result.method == DetectionMethod.RATIO
        assert ratio_result.is_anomaly is True

    def test_severity_calculation(self):
        """Test severity calculation."""
        detector = CostAnomalyDetector()

        # High confidence, high change ratio
        assert detector._calculate_severity(0.9, 1.0) == "critical"

        # Medium confidence
        assert detector._calculate_severity(0.6, 0.3) == "medium"


class TestCostExplorerClient:
    """Test suite for Cost Explorer client."""

    def test_client_creation(self):
        """Test CostExplorerClient creation."""
        client = CostExplorerClient(use_mock=True)

        assert client.use_mock is True

    def test_get_cost_and_usage(self):
        """Test cost and usage retrieval."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_and_usage(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        assert "results" in result
        assert len(result["results"]) > 0

    def test_get_cost_by_service(self):
        """Test cost by service retrieval."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_by_service(days=7)

        assert isinstance(result, dict)
        # Should have service entries

    def test_get_historical_costs_for_detector(self):
        """Test historical costs formatted for detector."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_historical_costs_for_detector(days=14)

        assert isinstance(result, dict)
        for service, data in result.items():
            assert "current_cost" in data
            assert "historical_costs" in data
            assert "timestamps" in data

    def test_get_cost_forecast(self):
        """Test cost forecast."""
        client = CostExplorerClient(use_mock=True)

        result = client.get_cost_forecast(
            start_date="2024-02-01",
            end_date="2024-02-15",
        )

        assert "total_forecast" in result
        assert result["total_forecast"] > 0
