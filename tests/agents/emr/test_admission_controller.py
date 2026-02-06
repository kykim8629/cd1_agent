"""Tests for AdmissionController."""

import os
import pytest
from src.common.services.aws_client import AWSClient, AWSProvider
from src.agents.emr.services.admission_controller import AdmissionController
from src.agents.emr.models.connection_limits import ConnectionLimits


@pytest.fixture(autouse=True)
def mock_mode():
    """Enable mock mode for all tests."""
    os.environ["AWS_MOCK"] = "true"
    yield
    os.environ.pop("AWS_MOCK", None)


class TestAdmissionController:
    """Tests for AdmissionController."""

    def setup_method(self):
        """Set up test fixtures."""
        self.aws_client = AWSClient(provider=AWSProvider.MOCK)
        self.controller = AdmissionController(self.aws_client)

        # Set up ADW limits (1000 connections, 95% threshold = 950)
        self.controller.registry.set_limits(ConnectionLimits.default_for_adw())
        # Clear any existing registrations
        self.controller.registry.clear_mock_registry()

    def test_acquire_allowed_when_empty(self):
        """Acquire allowed when no batches running."""
        result = self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_001",
            dag_run_id="batch_001_run_1",
            table_name="SALES_ORDER",
            parallel_hint=8,
        )

        assert result.allowed is True
        assert result.parallel == 8
        assert result.downgraded is False
        assert result.current_usage == 8

    def test_acquire_allowed_with_capacity(self):
        """Acquire allowed when capacity available."""
        # First batch
        self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_001",
            dag_run_id="batch_001_run_1",
            table_name="TABLE_A",
            parallel_hint=100,
        )

        # Second batch
        result = self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_002",
            dag_run_id="batch_002_run_1",
            table_name="TABLE_B",
            parallel_hint=50,
        )

        assert result.allowed is True
        assert result.parallel == 50
        assert result.current_usage == 150

    def test_acquire_downgraded_when_partial_capacity(self):
        """Acquire with downgrade when partial capacity available."""
        # Fill up most capacity (900 connections)
        for i in range(90):
            self.controller.check_admission(
                src_db_id=4,
                dag_id=f"batch_{i:03d}",
                dag_run_id=f"batch_{i:03d}_run_1",
                table_name=f"TABLE_{i}",
                parallel_hint=10,
            )

        # Verify current usage
        assert self.controller.registry.get_current_usage(4) == 900

        # Request 64, but only 50 available (950 - 900)
        # Should downgrade: 64 -> 32 (fits)
        result = self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_new",
            dag_run_id="batch_new_run_1",
            table_name="NEW_TABLE",
            parallel_hint=64,
        )

        assert result.allowed is True
        assert result.downgraded is True
        assert result.parallel <= 50  # Must fit
        assert result.original_parallel == 64

    def test_acquire_wait_when_no_capacity(self):
        """Acquire returns wait when no capacity."""
        # Fill up capacity completely (950 connections)
        for i in range(95):
            self.controller.check_admission(
                src_db_id=4,
                dag_id=f"batch_{i:03d}",
                dag_run_id=f"batch_{i:03d}_run_1",
                table_name=f"TABLE_{i}",
                parallel_hint=10,
            )

        # Verify current usage
        assert self.controller.registry.get_current_usage(4) == 950

        # Request when no capacity
        result = self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_blocked",
            dag_run_id="batch_blocked_run_1",
            table_name="BLOCKED_TABLE",
            parallel_hint=8,
        )

        assert result.allowed is False
        assert result.wait_seconds > 0
        assert result.reason == "connection_limit_exceeded"

    def test_release_success(self):
        """Release successfully returns connections."""
        # Acquire first
        self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_001",
            dag_run_id="batch_001_run_1",
            table_name="TABLE_A",
            parallel_hint=16,
        )

        # Verify usage
        assert self.controller.registry.get_current_usage(4) == 16

        # Release
        result = self.controller.release(
            src_db_id=4,
            dag_run_id="batch_001_run_1",
        )

        assert result.released is True
        assert result.released_connections == 16

        # Verify usage after release
        assert self.controller.registry.get_current_usage(4) == 0

    def test_release_not_found(self):
        """Release returns error when batch not found."""
        result = self.controller.release(
            src_db_id=4,
            dag_run_id="nonexistent_run",
        )

        assert result.released is False
        assert result.error is not None

    def test_status_summary(self):
        """Status returns correct summary."""
        # Add some batches
        for i in range(5):
            self.controller.check_admission(
                src_db_id=4,
                dag_id=f"batch_{i:03d}",
                dag_run_id=f"batch_{i:03d}_run_1",
                table_name=f"TABLE_{i}",
                parallel_hint=10,
            )

        status = self.controller.get_status()

        assert "sources" in status
        assert "4" in status["sources"]
        assert status["sources"]["4"]["current_usage"] == 50
        assert status["sources"]["4"]["active_batches"] == 5
        assert status["sources"]["4"]["max_connections"] == 1000

    def test_multiple_sources(self):
        """Controller handles multiple source databases."""
        # Add limits for another source
        self.controller.registry.set_limits(
            ConnectionLimits(
                src_db_id=5,
                name="ERP",
                db_type="oracle",
                max_connections=500,
            )
        )

        # Acquire from both sources
        self.controller.check_admission(
            src_db_id=4,
            dag_id="batch_adw",
            dag_run_id="batch_adw_run_1",
            table_name="ADW_TABLE",
            parallel_hint=8,
        )

        self.controller.check_admission(
            src_db_id=5,
            dag_id="batch_erp",
            dag_run_id="batch_erp_run_1",
            table_name="ERP_TABLE",
            parallel_hint=16,
        )

        status = self.controller.get_status()

        assert status["sources"]["4"]["current_usage"] == 8
        assert status["sources"]["5"]["current_usage"] == 16


class TestAdmissionControllerDowngrade:
    """Tests for downgrade logic."""

    def setup_method(self):
        """Set up test fixtures with small limits for easy testing."""
        os.environ["AWS_MOCK"] = "true"
        self.aws_client = AWSClient(provider=AWSProvider.MOCK)
        self.controller = AdmissionController(self.aws_client)

        # Small limits for testing (100 max, 95 threshold, min 2)
        self.controller.registry.set_limits(
            ConnectionLimits(
                src_db_id=99,
                name="TEST_DB",
                db_type="oracle",
                max_connections=100,
                threshold_percent=95,
                min_parallel=2,
            )
        )
        self.controller.registry.clear_mock_registry()

    def test_downgrade_halves_parallel(self):
        """Downgrade halves the parallel degree."""
        # Use 90 connections
        self.controller.check_admission(
            src_db_id=99,
            dag_id="filler",
            dag_run_id="filler_run",
            table_name="FILLER",
            parallel_hint=90,
        )

        # Request 16, only 5 available, should get 4 (16 -> 8 -> 4)
        result = self.controller.check_admission(
            src_db_id=99,
            dag_id="test",
            dag_run_id="test_run",
            table_name="TEST",
            parallel_hint=16,
        )

        assert result.allowed is True
        assert result.downgraded is True
        assert result.parallel == 4
        assert result.original_parallel == 16

    def test_downgrade_respects_minimum(self):
        """Downgrade respects minimum parallel."""
        # Use 94 connections (only 1 available, but min is 2)
        self.controller.check_admission(
            src_db_id=99,
            dag_id="filler",
            dag_run_id="filler_run",
            table_name="FILLER",
            parallel_hint=94,
        )

        # Request 8, can't fit even min (2), should wait
        result = self.controller.check_admission(
            src_db_id=99,
            dag_id="test",
            dag_run_id="test_run",
            table_name="TEST",
            parallel_hint=8,
        )

        assert result.allowed is False
