# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

from collections.abc import Collection
from typing import Any

from neuro_san.internals.validation.network.abstract_network_validator import AbstractNetworkValidator


class AgentNetworkAssembler:
    """
    Interface for a policy class that assembles an agent network from an agent network definition
    """

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    async def assemble_agent_network(
        self,
        network_def: dict[str, Any],
        top_agent_name: str,
        agent_network_name: str,
        sample_queries: list[str],
        client_token_mcp_urls: Collection[str] | None = None,
    ) -> Any:
        """
        Assemble the agent network from the definition.

        :param network_def: Agent network definition
        :param top_agent_name: The name of the top agent
        :param agent_network_name: The file name, without the .hocon extension
        :param sample_queries: List of sample queries for the agent network
        :param client_token_mcp_urls: Optional collection of MCP server URLs whose
                auth is client-supplied (the conversation's sly_data http_headers
                servers that are not configured in mcp_info.hocon). Drives the
                sly_data_schema emitted into the assembled network; None or empty
                means no schema is emitted.

        :return: Some representation of the agent network
        """
        raise NotImplementedError

    @staticmethod
    def build_mcp_sly_data_schema(
        network_def: dict[str, Any], client_token_mcp_urls: Collection[str] | None
    ) -> dict[str, Any] | None:
        """
        Build the sly_data_schema declaring the HTTP headers the assembled
        network's MCP tools need, for placement inside the front man's
        "function" block.

        Generic clients read this schema to learn what private inputs to
        supply outside the chat stream. In particular, nsflow reads
        properties.http_headers.properties to know which MCP server URLs to
        inject stored OAuth bearer tokens for (as
        sly_data["http_headers"][<url>]["Authorization"]), and
        properties.http_headers.required to know which of them must be
        connected before chat is allowed. See registries/tools/you_search.hocon
        for the hand-written reference of this exact shape.

        Only servers whose auth is client-supplied are declared — the ones
        the designing conversation itself provided headers for via sly_data
        (nsflow injects one per connected server). Servers configured in
        mcp_info.hocon are omitted entirely: their auth (if any) lives
        server-side, so a client has nothing to supply for them — matching
        you_search.hocon, which declares only its OAuth server. Every
        declared URL is also in `required`, so clients like nsflow gate
        chat until the user has connected it.

        :param network_def: Agent network definition. MCP server URLs are
                recognized as tools-list entries present in
                client_token_mcp_urls — a membership test, never URL pattern
                matching, since tools lists also hold agent names and
                subnetwork references.
        :param client_token_mcp_urls: MCP server URLs whose auth is
                client-supplied, or None.
        :return: The sly_data_schema dict, or None when the network uses no
                client-token MCP servers (no schema should be emitted at all).
        """
        if not client_token_mcp_urls:
            return None

        # Collect the client-token MCP URLs the network actually uses,
        # deduped in first-appearance order so the emitted schema is
        # deterministic. coerce_tools is the framework's guard for
        # malformed tools shapes (a str-valued tools field reads as []
        # instead of iterating characters), keeping this walk consistent
        # with neuro-san's own network validators.
        used_urls: dict[str, None] = {}
        for agent in network_def.values():
            if not isinstance(agent, dict):
                continue
            for tool in AbstractNetworkValidator.coerce_tools(agent):
                if isinstance(tool, str) and tool in client_token_mcp_urls:
                    used_urls[tool] = None
        if not used_urls:
            return None

        url_properties: dict[str, Any] = {}
        for url in used_urls:
            url_properties[url] = {
                "type": "object",
                "description": f"HTTP headers for the MCP server at {url}.",
                "properties": {
                    "Authorization": {
                        "type": "string",
                        "description": "Authorization header, e.g. 'Bearer <token_value>'.",
                    }
                },
                "required": ["Authorization"],
            }

        return {
            "type": "object",
            "properties": {
                "http_headers": {
                    "type": "object",
                    "description": "HTTP headers to be sent with MCP tool requests.",
                    "properties": url_properties,
                    "required": list(used_urls),
                }
            },
            "required": ["http_headers"],
        }
