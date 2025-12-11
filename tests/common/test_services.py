"""
Unit Tests for Common Services.

Tests for LLM and AWS client implementations.
"""

import pytest
from datetime import datetime, timedelta

from src.common.services.llm_client import LLMClient, LLMProvider, MockLLMProvider
from src.common.services.aws_client import AWSClient, AWSProvider, MockAWSProvider
from src.common.models.analysis_result import AnalysisResult


class TestLLMClient:
    """Test suite for LLM client."""

    def test_mock_provider_creation(self):
        """Test MockLLMProvider creation."""
        provider = MockLLMProvider()

        assert provider.call_history == []

    def test_mock_provider_generate(self):
        """Test MockLLMProvider generate method."""
        provider = MockLLMProvider()
        response = provider.generate("Test prompt")

        assert isinstance(response, str)
        assert len(provider.call_history) == 1
        assert provider.call_history[0]["method"] == "generate"

    def test_mock_provider_with_custom_response(self):
        """Test MockLLMProvider with custom responses."""
        custom_response = "Custom mock response"
        provider = MockLLMProvider(responses={"generate": custom_response})

        response = provider.generate("Test prompt")

        assert response == custom_response

    def test_llm_client_mock_provider(self):
        """Test LLMClient with mock provider."""
        client = LLMClient(provider=LLMProvider.MOCK)

        response = client.generate("Analyze this log")

        assert isinstance(response, str)
        assert "analysis" in response.lower() or "root_cause" in response.lower()

    def test_llm_client_generate_structured(self):
        """Test LLMClient structured generation."""
        client = LLMClient(provider=LLMProvider.MOCK)

        result = client.generate_structured(
            prompt="Analyze this anomaly",
            response_model=AnalysisResult,
        )

        assert isinstance(result, AnalysisResult)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_llm_client_call_history(self):
        """Test LLMClient call history tracking."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("First call")
        client.generate("Second call")

        assert len(client.call_history) == 2

    def test_llm_client_temperature_parameter(self):
        """Test LLMClient temperature parameter."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("Test", temperature=0.5)

        assert client.call_history[0]["temperature"] == 0.5

    def test_llm_client_system_prompt(self):
        """Test LLMClient with system prompt."""
        client = LLMClient(provider=LLMProvider.MOCK)

        client.generate("Test", system_prompt="You are an expert analyst.")

        assert client.call_history[0]["system_prompt"] == "You are an expert analyst."


class TestAWSClient:
    """Test suite for AWS client."""

    def test_mock_provider_creation(self):
        """Test MockAWSProvider creation."""
        provider = MockAWSProvider()

        assert provider.call_history == []

    def test_aws_client_mock_provider(self):
        """Test AWSClient with mock provider."""
        client = AWSClient(provider=AWSProvider.MOCK)

        assert client.provider_type == AWSProvider.MOCK

    def test_get_cloudwatch_metrics(self):
        """Test CloudWatch metrics retrieval."""
        client = AWSClient(provider=AWSProvider.MOCK)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        result = client.get_cloudwatch_metrics(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions=[{"FunctionName": "test-function"}],
            start_time=start_time,
            end_time=end_time,
        )

        assert "namespace" in result
        assert "datapoints" in result
        assert len(client.call_history) == 1

    def test_query_cloudwatch_logs(self):
        """Test CloudWatch Logs query."""
        client = AWSClient(provider=AWSProvider.MOCK)

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)

        result = client.query_cloudwatch_logs(
            log_group="/aws/lambda/test",
            query="fields @message",
            start_time=start_time,
            end_time=end_time,
        )

        assert isinstance(result, list)

    def test_put_dynamodb_item(self):
        """Test DynamoDB put item."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.put_dynamodb_item(
            table_name="test-table",
            item={"pk": "test-key", "data": "test-value"},
        )

        assert result["status"] == "success"

    def test_get_dynamodb_item(self):
        """Test DynamoDB get item."""
        client = AWSClient(provider=AWSProvider.MOCK)

        # First put
        client.put_dynamodb_item(
            table_name="test-table",
            item={"pk": "test-key", "data": "test-value"},
        )

        # Then get
        result = client.get_dynamodb_item(
            table_name="test-table",
            key={"pk": "test-key"},
        )

        assert result is not None
        assert result["pk"] == "test-key"

    def test_put_eventbridge_event(self):
        """Test EventBridge event publishing."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.put_eventbridge_event(
            event_bus="test-bus",
            source="bdp.test",
            detail_type="TestEvent",
            detail={"key": "value"},
        )

        assert result["failed_count"] == 0

    def test_retrieve_knowledge_base(self):
        """Test Knowledge Base retrieval."""
        client = AWSClient(provider=AWSProvider.MOCK)

        result = client.retrieve_knowledge_base(
            knowledge_base_id="test-kb",
            query="troubleshooting database",
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_mock_data_injection(self):
        """Test mock data injection."""
        mock_data = {
            "cloudwatch_metrics": {
                "namespace": "Custom",
                "metric": "CustomMetric",
                "datapoints": [{"Sum": 100}],
            }
        }

        client = AWSClient(provider=AWSProvider.MOCK, mock_data=mock_data)

        result = client.get_cloudwatch_metrics(
            namespace="Custom",
            metric_name="CustomMetric",
            dimensions=[],
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
        )

        assert result["namespace"] == "Custom"

    def test_get_events(self):
        """Test retrieving stored events."""
        client = AWSClient(provider=AWSProvider.MOCK)

        client.put_eventbridge_event(
            event_bus="test-bus",
            source="bdp.test",
            detail_type="TestEvent",
            detail={"key": "value"},
        )

        events = client.get_events()

        assert len(events) == 1
        assert events[0]["source"] == "bdp.test"
