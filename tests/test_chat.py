"""
Chat 모듈 테스트.

Interactive Chat 기능 단위 테스트.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.chat.state import (
    ChatState, ChatStateDict, ChatMessage, MessageRole, ChatPhase,
    ToolExecution, ReflectionResult, ApprovalRequest, ApprovalStatus
)
from src.chat.config import ChatConfig, get_config, get_prompts
from src.chat.agent import ChatAgent
from src.services.llm_client import LLMProvider
from src.services.aws_client import AWSProvider


class TestChatState:
    """ChatState 모델 테스트."""

    def test_chat_message_creation(self):
        """ChatMessage 생성 테스트."""
        msg = ChatMessage(
            role=MessageRole.USER,
            content="테스트 메시지",
        )

        assert msg.role == MessageRole.USER
        assert msg.content == "테스트 메시지"
        assert isinstance(msg.timestamp, datetime)

    def test_chat_message_to_dict(self):
        """ChatMessage 딕셔너리 변환 테스트."""
        msg = ChatMessage(
            role=MessageRole.ASSISTANT,
            content="응답 메시지",
            metadata={"confidence": 0.85},
        )

        d = msg.to_dict()

        assert d["role"] == "assistant"
        assert d["content"] == "응답 메시지"
        assert d["metadata"]["confidence"] == 0.85

    def test_chat_state_add_message(self):
        """ChatState 메시지 추가 테스트."""
        state = ChatState()
        state.add_message(MessageRole.USER, "안녕하세요")
        state.add_message(MessageRole.ASSISTANT, "반갑습니다")

        assert len(state.messages) == 2
        assert state.messages[0].role == MessageRole.USER
        assert state.messages[1].role == MessageRole.ASSISTANT

    def test_chat_state_conversation_context(self):
        """대화 컨텍스트 생성 테스트."""
        state = ChatState()
        state.add_message(MessageRole.USER, "질문입니다")
        state.add_message(MessageRole.ASSISTANT, "답변입니다")

        context = state.get_conversation_context()

        assert "User: 질문입니다" in context
        assert "Assistant: 답변입니다" in context

    def test_tool_execution(self):
        """ToolExecution 테스트."""
        execution = ToolExecution(
            tool_name="get_service_health",
            input_params={"service_name": "test"},
            output={"status": "healthy"},
            success=True,
            execution_time_ms=150,
        )

        d = execution.to_dict()

        assert d["tool_name"] == "get_service_health"
        assert d["success"] is True
        assert d["execution_time_ms"] == 150

    def test_reflection_result(self):
        """ReflectionResult 테스트."""
        reflection = ReflectionResult(
            confidence=0.75,
            needs_replan=False,
            needs_human_review=True,
            reasoning="신뢰도가 임계값 이하",
            concerns=["추가 검증 필요"],
        )

        assert reflection.confidence == 0.75
        assert reflection.needs_human_review is True
        assert len(reflection.concerns) == 1

    def test_approval_request(self):
        """ApprovalRequest 테스트."""
        request = ApprovalRequest(
            request_id="test-123",
            action_type="pod_restart",
            description="Pod 재시작 필요",
            parameters={"pod_name": "test-pod"},
            confidence=0.82,
            expected_impact="일시적 서비스 중단",
        )

        assert request.status == ApprovalStatus.PENDING
        assert request.action_type == "pod_restart"

        d = request.to_dict()
        assert d["request_id"] == "test-123"
        assert d["status"] == "pending"


class TestChatConfig:
    """ChatConfig 테스트."""

    def test_default_config(self):
        """기본 설정 테스트."""
        config = get_config()

        assert config.max_iterations == 5 or config.max_iterations > 0
        assert config.confidence_threshold > 0
        assert config.require_approval_for_actions is True

    def test_prompts(self):
        """프롬프트 템플릿 테스트."""
        prompts = get_prompts()

        assert prompts.system_prompt is not None
        assert len(prompts.system_prompt) > 0
        assert "{context}" in prompts.plan_prompt
        assert "{user_input}" in prompts.plan_prompt


class TestChatAgent:
    """ChatAgent 테스트."""

    def test_agent_initialization(self):
        """에이전트 초기화 테스트."""
        agent = ChatAgent(
            llm_provider=LLMProvider.MOCK,
            aws_provider=AWSProvider.MOCK,
        )

        assert agent.session_id is not None
        assert len(agent.conversation_history) == 0
        assert agent.graph is not None

    def test_agent_chat_basic(self):
        """기본 채팅 테스트."""
        agent = ChatAgent(
            llm_provider=LLMProvider.MOCK,
            aws_provider=AWSProvider.MOCK,
        )

        response = agent.chat("안녕하세요")

        assert response is not None
        assert len(response) > 0
        assert len(agent.conversation_history) == 2  # user + assistant

    def test_agent_conversation_history(self):
        """대화 히스토리 테스트."""
        agent = ChatAgent(
            llm_provider=LLMProvider.MOCK,
            aws_provider=AWSProvider.MOCK,
        )

        agent.chat("첫 번째 질문")
        agent.chat("두 번째 질문")

        history = agent.get_conversation_history()

        assert len(history) == 4  # 2 user + 2 assistant
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_agent_clear_history(self):
        """히스토리 초기화 테스트."""
        agent = ChatAgent(
            llm_provider=LLMProvider.MOCK,
            aws_provider=AWSProvider.MOCK,
        )

        agent.chat("테스트")
        assert len(agent.conversation_history) > 0

        agent.clear_history()
        assert len(agent.conversation_history) == 0

    def test_agent_status(self):
        """에이전트 상태 조회 테스트."""
        agent = ChatAgent(
            llm_provider=LLMProvider.MOCK,
            aws_provider=AWSProvider.MOCK,
        )

        status = agent.get_status()

        assert "session_id" in status
        assert "conversation_length" in status
        assert "current_phase" in status
        assert status["conversation_length"] == 0


class TestChatTools:
    """Chat Tools 테스트."""

    def test_create_chat_tools(self):
        """Tool 생성 테스트."""
        from src.chat.tools import create_chat_tools
        from src.services.aws_client import AWSClient

        aws_client = AWSClient(provider=AWSProvider.MOCK)
        tools = create_chat_tools(aws_client)

        assert "get_cloudwatch_metrics" in tools
        assert "query_cloudwatch_logs" in tools
        assert "get_service_health" in tools
        assert "get_prometheus_metrics" in tools
        assert "get_pod_status" in tools

    def test_prometheus_tools(self):
        """Prometheus Tool 테스트."""
        from src.chat.tools.prometheus import get_prometheus_metrics, get_pod_status

        # 메트릭 조회
        result = get_prometheus_metrics(query="up")
        assert result["success"] is True

        # Pod 상태 조회
        result = get_pod_status(namespace="spark")
        assert result["success"] is True
        assert "pods" in result
        assert "summary" in result


class TestChatNodes:
    """Chat Graph Nodes 테스트."""

    def test_plan_node(self):
        """Plan 노드 테스트."""
        from src.chat.nodes.plan import create_plan_node
        from src.services.llm_client import LLMClient

        llm_client = LLMClient(provider=LLMProvider.MOCK)
        plan_node = create_plan_node(llm_client)

        state: ChatStateDict = {
            "messages": [],
            "user_input": "서비스 상태 확인해줘",
            "phase": "idle",
            "current_plan": None,
            "tool_executions": [],
            "observation": None,
            "analysis_result": None,
            "reflection": None,
            "confidence_score": 0.0,
            "pending_approval": None,
            "iteration_count": 0,
            "max_iterations": 5,
            "should_continue": True,
            "response": None,
            "session_id": "test",
        }

        result = plan_node(state)

        assert "current_plan" in result
        assert "phase" in result
        assert result["phase"] == "planning"

    def test_reflect_node(self):
        """Reflect 노드 테스트."""
        from src.chat.nodes.reflect import create_reflect_node
        from src.services.llm_client import LLMClient

        llm_client = LLMClient(provider=LLMProvider.MOCK)
        reflect_node = create_reflect_node(llm_client)

        state: ChatStateDict = {
            "messages": [],
            "user_input": "테스트",
            "phase": "observing",
            "current_plan": '{"intent": "테스트"}',
            "tool_executions": [],
            "observation": "관찰 결과입니다",
            "analysis_result": None,
            "reflection": None,
            "confidence_score": 0.0,
            "pending_approval": None,
            "iteration_count": 1,
            "max_iterations": 5,
            "should_continue": True,
            "response": None,
            "session_id": "test",
        }

        result = reflect_node(state)

        assert "reflection" in result
        assert "confidence_score" in result
        assert result["phase"] == "reflecting"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
