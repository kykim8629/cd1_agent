"""
Unit Tests for Drift Agent Services.

Tests for Config Fetcher, Drift Detector, and GitLab Client.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestConfigFetcher:
    """Test suite for Config Fetcher."""

    @pytest.fixture
    def fetcher(self):
        """Create fetcher instance with mock provider."""
        from src.agents.drift.services.config_fetcher import ConfigFetcher, ConfigProvider
        return ConfigFetcher(provider=ConfigProvider.MOCK)

    def test_fetcher_creation(self, fetcher):
        """Test ConfigFetcher creation."""
        assert fetcher is not None

    def test_get_config(self, fetcher):
        """Test fetching current configuration."""
        from src.agents.drift.services.config_fetcher import ResourceType, ResourceConfig

        # Use mock data resource_id: production-eks
        result = fetcher.get_config(
            resource_type=ResourceType.EKS,
            resource_id="production-eks",
        )

        assert isinstance(result, ResourceConfig)


class TestDriftDetector:
    """Test suite for Drift Detector."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        from src.agents.drift.services.drift_detector import ConfigDriftDetector
        return ConfigDriftDetector()

    def test_detector_creation(self, detector):
        """Test ConfigDriftDetector creation."""
        assert detector is not None

    def test_detect_drift(self, detector):
        """Test drift detection with changes."""
        from src.agents.drift.services.drift_detector import DriftResult

        baseline = {
            "setting_a": "value_a",
            "setting_b": 100,
        }
        current = {
            "setting_a": "value_a",
            "setting_b": 200,  # Changed
        }

        result = detector.detect(
            baseline=baseline,
            current=current,
            resource_type="EKS",
            resource_id="test-cluster",
        )

        assert isinstance(result, DriftResult)

    def test_detect_no_drift(self, detector):
        """Test detection with no drift."""
        from src.agents.drift.services.drift_detector import DriftResult

        config = {
            "setting_a": "value_a",
            "setting_b": 100,
        }

        result = detector.detect(
            baseline=config,
            current=config,
            resource_type="EKS",
            resource_id="test-cluster",
        )

        assert isinstance(result, DriftResult)
        assert result.has_drift is False


class TestGitLabClient:
    """Test suite for GitLab Client."""

    @pytest.fixture
    def client(self):
        """Create client instance."""
        with patch.dict(
            "os.environ",
            {"GITLAB_TOKEN": "mock-token"},
        ):
            from src.agents.drift.services.gitlab_client import GitLabClient, GitLabProvider
            return GitLabClient(provider=GitLabProvider.MOCK)

    def test_client_creation(self, client):
        """Test GitLabClient creation."""
        assert client is not None

    def test_get_baseline_file_not_found(self, client):
        """Test getting baseline file returns error for non-existent file."""
        import pytest

        with pytest.raises(FileNotFoundError):
            client.get_baseline_file(
                file_path="config/nonexistent.yaml",
            )

    def test_list_baselines(self, client):
        """Test listing baseline files."""
        result = client.list_baselines()

        assert isinstance(result, list)
