"""
GitLab Client with Provider Abstraction.

Supports real GitLab API and mock providers for testing.
Used by Drift Agent to fetch configuration baselines from GitLab.
"""

import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class GitLabProvider(str, Enum):
    """Supported GitLab provider modes."""

    REAL = "real"
    MOCK = "mock"


@dataclass
class BaselineFile:
    """Represents a baseline configuration file from GitLab."""

    file_path: str
    content: Dict[str, Any]
    commit_sha: str
    last_modified: str
    ref: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "content": self.content,
            "commit_sha": self.commit_sha,
            "last_modified": self.last_modified,
            "ref": self.ref,
        }


class BaseGitLabProvider(ABC):
    """Abstract base class for GitLab providers."""

    @abstractmethod
    def get_file(
        self,
        project_id: str,
        file_path: str,
        ref: str = "main",
    ) -> BaselineFile:
        """Get file content from GitLab repository."""
        pass

    @abstractmethod
    def list_files(
        self,
        project_id: str,
        path: str,
        ref: str = "main",
        recursive: bool = False,
    ) -> List[str]:
        """List files in a directory."""
        pass

    @abstractmethod
    def get_commit_info(
        self,
        project_id: str,
        ref: str = "main",
    ) -> Dict[str, Any]:
        """Get commit information for a ref."""
        pass


class RealGitLabProvider(BaseGitLabProvider):
    """Real GitLab API provider."""

    def __init__(
        self,
        base_url: str,
        private_token: str,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.private_token = private_token
        self.timeout = timeout
        self._session = None

    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers["PRIVATE-TOKEN"] = self.private_token
        return self._session

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make HTTP request to GitLab API."""
        session = self._get_session()
        url = f"{self.base_url}{endpoint}"

        try:
            response = session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"GitLab API error: {e}")
            raise

    def get_file(
        self,
        project_id: str,
        file_path: str,
        ref: str = "main",
    ) -> BaselineFile:
        """Get file content from GitLab repository."""
        encoded_path = quote(file_path, safe="")
        encoded_project = quote(str(project_id), safe="")

        # Get file content
        endpoint = f"/projects/{encoded_project}/repository/files/{encoded_path}"
        response = self._make_request(endpoint, {"ref": ref})
        file_data = response.json()

        # Decode base64 content
        content_bytes = base64.b64decode(file_data["content"])
        content = json.loads(content_bytes.decode("utf-8"))

        return BaselineFile(
            file_path=file_path,
            content=content,
            commit_sha=file_data.get("commit_id", ""),
            last_modified=file_data.get("last_commit_id", ""),
            ref=ref,
        )

    def list_files(
        self,
        project_id: str,
        path: str,
        ref: str = "main",
        recursive: bool = False,
    ) -> List[str]:
        """List files in a directory."""
        encoded_project = quote(str(project_id), safe="")
        endpoint = f"/projects/{encoded_project}/repository/tree"

        params = {
            "path": path,
            "ref": ref,
            "recursive": str(recursive).lower(),
        }

        response = self._make_request(endpoint, params)
        items = response.json()

        return [
            item["path"]
            for item in items
            if item["type"] == "blob" and item["path"].endswith(".json")
        ]

    def get_commit_info(
        self,
        project_id: str,
        ref: str = "main",
    ) -> Dict[str, Any]:
        """Get commit information for a ref."""
        encoded_project = quote(str(project_id), safe="")
        encoded_ref = quote(ref, safe="")
        endpoint = f"/projects/{encoded_project}/repository/commits/{encoded_ref}"

        response = self._make_request(endpoint)
        commit_data = response.json()

        return {
            "sha": commit_data.get("id", ""),
            "short_sha": commit_data.get("short_id", ""),
            "message": commit_data.get("message", ""),
            "author_name": commit_data.get("author_name", ""),
            "authored_date": commit_data.get("authored_date", ""),
        }


class MockGitLabProvider(BaseGitLabProvider):
    """Mock GitLab provider for testing."""

    def __init__(self):
        self._baselines: Dict[str, Dict[str, Any]] = {}
        self._setup_default_baselines()

    def _setup_default_baselines(self):
        """Setup default mock baselines."""
        # EKS baseline
        self.set_baseline("baselines/eks/production-cluster.json", {
            "cluster_name": "production-eks",
            "version": "1.29",
            "endpoint_public_access": False,
            "endpoint_private_access": True,
            "logging": {
                "api": True,
                "audit": True,
                "authenticator": True,
                "controllerManager": True,
                "scheduler": True,
            },
            "node_groups": [
                {
                    "name": "general-workload",
                    "instance_types": ["m6i.xlarge", "m6i.2xlarge"],
                    "scaling_config": {
                        "min_size": 3,
                        "max_size": 10,
                        "desired_size": 5,
                    },
                    "disk_size": 100,
                    "ami_type": "AL2_x86_64",
                    "capacity_type": "ON_DEMAND",
                }
            ],
            "tags": {
                "Environment": "production",
                "ManagedBy": "bdp-agent",
            },
        })

        # MSK baseline
        self.set_baseline("baselines/msk/production-kafka.json", {
            "cluster_name": "production-kafka",
            "kafka_version": "3.5.1",
            "broker_config": {
                "instance_type": "kafka.m5.large",
                "number_of_broker_nodes": 3,
                "storage_info": {
                    "ebs_storage_info": {
                        "volume_size": 1000,
                        "provisioned_throughput": {
                            "enabled": True,
                            "volume_throughput": 250,
                        },
                    },
                },
            },
            "encryption_info": {
                "encryption_at_rest": True,
                "encryption_in_transit": "TLS",
            },
            "enhanced_monitoring": "PER_TOPIC_PER_BROKER",
            "tags": {
                "Environment": "production",
            },
        })

        # S3 baseline
        self.set_baseline("baselines/s3/data-lake-bucket.json", {
            "bucket_name": "company-data-lake-prod",
            "versioning": {
                "status": "Enabled",
            },
            "encryption": {
                "sse_algorithm": "aws:kms",
                "kms_master_key_id": "alias/data-lake-key",
                "bucket_key_enabled": True,
            },
            "public_access_block": {
                "block_public_acls": True,
                "ignore_public_acls": True,
                "block_public_policy": True,
                "restrict_public_buckets": True,
            },
            "tags": {
                "Environment": "production",
                "DataClassification": "confidential",
            },
        })

        # EMR baseline
        self.set_baseline("baselines/emr/analytics-cluster.json", {
            "cluster_name": "analytics-emr-prod",
            "release_label": "emr-7.0.0",
            "applications": ["Spark", "Hadoop", "Hive"],
            "instance_groups": {
                "master": {
                    "instance_type": "m5.xlarge",
                    "instance_count": 1,
                },
                "core": {
                    "instance_type": "r5.2xlarge",
                    "instance_count": 4,
                },
            },
            "tags": {
                "Environment": "production",
            },
        })

        # MWAA baseline
        self.set_baseline("baselines/mwaa/orchestration-env.json", {
            "environment_name": "bdp-airflow-prod",
            "airflow_version": "2.8.1",
            "environment_class": "mw1.medium",
            "min_workers": 2,
            "max_workers": 10,
            "schedulers": 2,
            "webserver_access_mode": "PRIVATE_ONLY",
            "tags": {
                "Environment": "production",
            },
        })

    def set_baseline(
        self,
        file_path: str,
        content: Dict[str, Any],
        commit_sha: str = "abc123def456",
    ) -> None:
        """Set mock baseline for a file path."""
        self._baselines[file_path] = {
            "content": content,
            "commit_sha": commit_sha,
            "last_modified": "2024-01-01T00:00:00Z",
        }

    def get_file(
        self,
        project_id: str,
        file_path: str,
        ref: str = "main",
    ) -> BaselineFile:
        """Get file content from mock repository."""
        logger.debug(f"Mock GitLab get_file: {file_path}")

        if file_path not in self._baselines:
            raise FileNotFoundError(f"Baseline not found: {file_path}")

        baseline = self._baselines[file_path]

        return BaselineFile(
            file_path=file_path,
            content=baseline["content"],
            commit_sha=baseline["commit_sha"],
            last_modified=baseline["last_modified"],
            ref=ref,
        )

    def list_files(
        self,
        project_id: str,
        path: str,
        ref: str = "main",
        recursive: bool = False,
    ) -> List[str]:
        """List files in mock directory."""
        logger.debug(f"Mock GitLab list_files: {path}")

        files = []
        for file_path in self._baselines.keys():
            if file_path.startswith(path):
                if recursive or "/" not in file_path[len(path) + 1:]:
                    files.append(file_path)

        return files

    def get_commit_info(
        self,
        project_id: str,
        ref: str = "main",
    ) -> Dict[str, Any]:
        """Get mock commit information."""
        return {
            "sha": "abc123def456789",
            "short_sha": "abc123d",
            "message": "Mock commit for testing",
            "author_name": "Mock User",
            "authored_date": "2024-01-01T00:00:00Z",
        }


class GitLabClient:
    """GitLab client with automatic provider selection."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        private_token: Optional[str] = None,
        project_id: Optional[str] = None,
        baseline_path: str = "baselines",
        baseline_ref: str = "main",
        provider: Optional[GitLabProvider] = None,
    ):
        """
        Initialize GitLab client.

        Args:
            base_url: GitLab API base URL
            private_token: GitLab private access token
            project_id: GitLab project ID for baselines
            baseline_path: Path to baseline files in repository
            baseline_ref: Git ref (branch/tag) for baselines
            provider: Force specific provider (auto-detect if None)
        """
        self.base_url = base_url or os.environ.get(
            "GITLAB_BASE_URL", "https://gitlab.com/api/v4"
        )
        self.private_token = private_token or os.environ.get("GITLAB_PRIVATE_TOKEN", "")
        self.project_id = project_id or os.environ.get("GITLAB_PROJECT_ID", "")
        self.baseline_path = baseline_path or os.environ.get(
            "GITLAB_BASELINE_PATH", "baselines"
        )
        self.baseline_ref = baseline_ref or os.environ.get(
            "GITLAB_BASELINE_REF", "main"
        )

        # Auto-detect provider
        if provider is None:
            if os.environ.get("GITLAB_MOCK", "").lower() == "true":
                provider = GitLabProvider.MOCK
            elif os.environ.get("AWS_MOCK", "").lower() == "true":
                # If AWS is mocked, also mock GitLab
                provider = GitLabProvider.MOCK
            elif not self.private_token:
                # No token available, use mock
                provider = GitLabProvider.MOCK
            else:
                provider = GitLabProvider.REAL

        self.provider_type = provider

        if provider == GitLabProvider.MOCK:
            self._provider = MockGitLabProvider()
            logger.info("Using Mock GitLab Provider")
        else:
            self._provider = RealGitLabProvider(
                base_url=self.base_url,
                private_token=self.private_token,
            )
            logger.info(f"Using Real GitLab Provider: {self.base_url}")

    @property
    def provider(self) -> BaseGitLabProvider:
        """Get the underlying provider."""
        return self._provider

    def get_baseline_file(
        self,
        file_path: str,
        ref: Optional[str] = None,
    ) -> BaselineFile:
        """Get baseline configuration file."""
        return self._provider.get_file(
            project_id=self.project_id,
            file_path=file_path,
            ref=ref or self.baseline_ref,
        )

    def get_resource_baseline(
        self,
        resource_type: str,
        resource_name: str,
        ref: Optional[str] = None,
    ) -> BaselineFile:
        """
        Get baseline for a specific resource.

        Args:
            resource_type: Resource type (eks, msk, s3, emr, mwaa)
            resource_name: Resource identifier
            ref: Git ref to use

        Returns:
            BaselineFile with configuration baseline
        """
        file_path = f"{self.baseline_path}/{resource_type.lower()}/{resource_name}.json"
        return self.get_baseline_file(file_path, ref)

    def list_baselines(
        self,
        resource_type: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> List[str]:
        """
        List available baseline files.

        Args:
            resource_type: Filter by resource type (eks, msk, etc.)
            ref: Git ref to use

        Returns:
            List of baseline file paths
        """
        path = self.baseline_path
        if resource_type:
            path = f"{self.baseline_path}/{resource_type.lower()}"

        return self._provider.list_files(
            project_id=self.project_id,
            path=path,
            ref=ref or self.baseline_ref,
            recursive=True,
        )

    def get_commit_info(
        self,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get current commit information."""
        return self._provider.get_commit_info(
            project_id=self.project_id,
            ref=ref or self.baseline_ref,
        )


# Module-level convenience function
def get_gitlab_client(
    base_url: Optional[str] = None,
    private_token: Optional[str] = None,
) -> GitLabClient:
    """Get GitLab client instance."""
    return GitLabClient(base_url=base_url, private_token=private_token)


if __name__ == "__main__":
    # Test mock provider
    os.environ["GITLAB_MOCK"] = "true"

    client = GitLabClient()
    print(f"Provider type: {client.provider_type}")

    # Test baseline retrieval
    print("\n=== EKS Baseline ===")
    baseline = client.get_resource_baseline("eks", "production-cluster")
    print(f"  Cluster: {baseline.content.get('cluster_name')}")
    print(f"  Version: {baseline.content.get('version')}")
    print(f"  Commit: {baseline.commit_sha}")

    print("\n=== MSK Baseline ===")
    baseline = client.get_resource_baseline("msk", "production-kafka")
    print(f"  Cluster: {baseline.content.get('cluster_name')}")
    print(f"  Kafka Version: {baseline.content.get('kafka_version')}")

    print("\n=== List All Baselines ===")
    baselines = client.list_baselines()
    for b in baselines:
        print(f"  - {b}")
