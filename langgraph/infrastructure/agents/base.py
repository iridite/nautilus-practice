"""Base agent class for LangGraph workflows"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from langgraph.infrastructure.graph.state import AgentMessage
from langgraph.infrastructure.llm.claude_client import ClaudeClient
from langgraph.shared.logging import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """基础 Agent 类"""

    def __init__(self, name: str, llm_client: ClaudeClient):
        """
        初始化 Agent

        Args:
            name: Agent 名称
            llm_client: LLM 客户端
        """
        self.name = name
        self.llm_client = llm_client

        logger.info(f"Agent initialized: {name}")

    @abstractmethod
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        处理状态并返回更新后的状态

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        pass

    def create_message(self, content: str, metadata: dict[str, Any] | None = None) -> AgentMessage:
        """
        创建 Agent 消息

        Args:
            content: 消息内容
            metadata: 元数据（可选）

        Returns:
            AgentMessage 对象
        """
        return AgentMessage(
            agent=self.name,
            content=content,
            timestamp=datetime.utcnow(),
            metadata=metadata or {},
        )

    def add_message(
        self, state: dict[str, Any], content: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """
        向状态添加消息

        Args:
            state: 当前状态
            content: 消息内容
            metadata: 元数据（可选）
        """
        message = self.create_message(content, metadata)
        if "messages" not in state:
            state["messages"] = []
        state["messages"].append(message)

        logger.debug(f"Message added by {self.name}", content_length=len(content))
