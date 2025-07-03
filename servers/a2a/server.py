
"""
A2A server example
See https://github.com/google/a2a-python/tree/main/examples
and https://google.github.io/A2A/specification

Before running this server
 - cloning the repo from https://github.com/google/a2a-python/tree/main then `pip install .`
 - install crewai
 - run server by `python server.py`
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

# pylint: disable=import-error
import click

from a2a.server import A2AServer
from a2a.server.request_handlers import DefaultA2ARequestHandler
from a2a.types import AgentAuthentication
from a2a.types import AgentCapabilities
from a2a.types import AgentCard
from a2a.types import AgentSkill

from agent_executor import CrewAiAgentExecutor


@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=9999)
def main(host: str, port: int):
    """
    Starts the A2A server with the specified host and port.

    :param host: The hostname or IP address where the server will run.
    :param port: The port number on which the server will listen.
    """

    # Agent Skill describes a specific capability, function, or area of expertise the agent
    skill = AgentSkill(
        id="Research_Report",
        name="Research_Report",
        description="Return bullet points on a given topic",
        tags=["research", "report"],
        examples=["ai"],
    )

    # Agent Card is a JSON document that describes the server's identity, capabilities, skills,
    # and service endpoint URL
    agent_card = AgentCard(
        name="CrewAI Research Report Agent",
        description="Agent that does research and returns report on a given topic",
        url=f"http://{host}:{port}/",
        version='1.0.0',
        defaultInputModes=['text'],
        defaultOutputModes=['text'],
        capabilities=AgentCapabilities(),
        skills=[skill],
        authentication=AgentAuthentication(schemes=['public']),
    )

    request_handler = DefaultA2ARequestHandler(
        agent_executor=CrewAiAgentExecutor()
    )

    server = A2AServer(agent_card=agent_card, request_handler=request_handler)
    server.start(host=host, port=port)


if __name__ == '__main__':
    main()
