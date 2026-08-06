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

from typing import Any


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
        mcp_servers_auth: dict[str, bool] | None = None,
    ) -> Any:
        """
        Assemble the agent network from the definition.

        :param network_def: Agent network definition
        :param top_agent_name: The name of the top agent
        :param agent_network_name: The file name, without the .hocon extension
        :param sample_queries: List of sample queries for the agent network
        :param mcp_servers_auth: Optional {MCP server URL: needs_client_token} mapping
                for every known MCP server (see GetMcpTool.get_mcp_servers_auth_info).
                Drives the sly_data_schema emitted into the assembled network;
                None or {} means no schema is emitted.

        :return: Some representation of the agent network
        """
        raise NotImplementedError

    @staticmethod
    def build_mcp_sly_data_schema(
        network_def: dict[str, Any], mcp_servers_auth: dict[str, bool] | None
    ) -> dict[str, Any] | None:
        """
        Build the sly_data_schema declaring the HTTP headers the assembled
        network's MCP tools need, for placement inside the front man's
        "function" block.

        Generic clients read this schema to learn what private inputs to
        supply outside the chat stream. In particular, nsflow reads
        properties.http_headers.properties to know which MCP server URLs to
        opportunistically inject stored OAuth bearer tokens for (as
        sly_data["http_headers"][<url>]["Authorization"]), and
        properties.http_headers.required to know which of them must be
        connected before chat is allowed. See registries/tools/you_search.hocon
        for the hand-written reference of this exact shape.

        The `required` list is data-driven: a URL is required only when it
        needs a client-supplied token (no http_headers configured for it in
        mcp_info.hocon — the mapping computed by
        GetMcpTool.get_mcp_servers_auth_info). The key is always emitted,
        even when empty: omitting `required` makes nsflow gate every
        declared URL, while [] disables the gate but keeps opportunistic
        token injection.

        :param network_def: Agent network definition. MCP server URLs are
                recognized as tools-list entries present in mcp_servers_auth —
                a set intersection, never URL pattern matching, since tools
                lists also hold agent names and subnetwork references.
        :param mcp_servers_auth: {MCP server URL: needs_client_token} for every
                known MCP server, or None.
        :return: The sly_data_schema dict, or None when the network uses no
                MCP servers (no schema should be emitted at all).
        """
        if not mcp_servers_auth:
            return None

        # Collect the MCP URLs the network actually uses, deduped in
        # first-appearance order so the emitted schema is deterministic.
        used_urls: dict[str, None] = {}
        for agent in network_def.values():
            if not isinstance(agent, dict):
                continue
            for tool in agent.get("tools") or []:
                if isinstance(tool, str) and tool in mcp_servers_auth:
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
                    "required": [url for url in used_urls if mcp_servers_auth.get(url)],
                }
            },
            "required": ["http_headers"],
        }
