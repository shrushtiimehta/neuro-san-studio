
"""
crewAI agent executor for an A2A server example
See https://github.com/google/a2a-python/tree/main/examples
"""

# Copyright (C) 2023-2025 Cognizant Digital Business, Evolutionary AI.
# All Rights Reserved.
# Issued under the Academic Public License.
#
# You can be released from the terms, and requirements of the Academic Public
# License by purchasing a commercial license.
# Purchase of a commercial license is mandatory for any use of the
# neuro-san SDK Software in commercial settings.
#
# END COPYRIGHT

from typing import Any
from uuid import uuid4
from typing_extensions import override

# pylint: disable=import-error
from a2a.server.agent_execution import BaseAgentExecutor
from a2a.server.events import EventQueue
from a2a.types import Message
from a2a.types import MessageSendParams
from a2a.types import Part
from a2a.types import Role
from a2a.types import SendMessageRequest
from a2a.types import Task
from a2a.types import TextPart

from agent import CrewAiResearchReport


class CrewAiAgentExecutor(BaseAgentExecutor):
    """Agent executor for crewAI agents"""

    def __init__(self):
        self.agent = CrewAiResearchReport()

    @override
    async def on_message_send(
        self,
        request: SendMessageRequest,
        event_queue: EventQueue,
        task: Task | None,
    ) -> None:

        # Get topic from the request message
        params: MessageSendParams = request.params
        topic: str = self._get_user_query(params)

        # invoke the underlying agent
        agent_response: dict[str, Any] = await self.agent.ainvoke(topic)

        # return response message
        message: Message = Message(
            role=Role.agent,
            parts=[Part(TextPart(text=agent_response))],
            messageId=str(uuid4()),
        )
        event_queue.enqueue_event(message)

    def _get_user_query(self, task_send_params: MessageSendParams) -> str:
        """Helper to get user query from task send params."""
        part = task_send_params.message.parts[0].root
        if not isinstance(part, TextPart):
            raise ValueError('Only text parts are supported')
        return part.text
