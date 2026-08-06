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

"""Tests for the shared MCP sly_data_schema builder on AgentNetworkAssembler."""

from middleware.agent_network_designer.persistence.agent_network_assembler import AgentNetworkAssembler

OAUTH_URL = "https://oauth.example.com/mcp"
FILE_AUTH_URL = "https://file-auth.example.com/mcp"
UNUSED_URL = "https://unused.example.com/mcp"

# needs_client_token per server, as GetMcpTool.get_mcp_servers_auth_info returns it.
MCP_SERVERS_AUTH: dict[str, bool] = {OAUTH_URL: True, FILE_AUTH_URL: False, UNUSED_URL: True}

NETWORK_DEF: dict = {
    "front_man": {"description": "top", "instructions": "Coordinate.", "tools": ["helper", OAUTH_URL]},
    "helper": {
        "description": "helps",
        "instructions": "Help.",
        "tools": [FILE_AUTH_URL, "/sub_network", "ddgs_search"],
    },
    "ddgs_search": {},
}


class TestBuildMcpSlyDataSchema:
    """The schema builder both assemblers share."""

    def test_no_auth_info_means_no_schema(self):
        """None and {} both mean 'nothing known about MCP servers' — emit nothing."""
        assert AgentNetworkAssembler.build_mcp_sly_data_schema(NETWORK_DEF, None) is None
        assert AgentNetworkAssembler.build_mcp_sly_data_schema(NETWORK_DEF, {}) is None

    def test_a_network_using_no_mcp_servers_gets_no_schema(self):
        """Agent names and subnetwork refs in tools lists must not trigger a schema."""
        network_def = {
            "front_man": {"instructions": "Coordinate.", "tools": ["helper", "/sub_network"]},
            "helper": {"instructions": "Help."},
        }
        assert AgentNetworkAssembler.build_mcp_sly_data_schema(network_def, MCP_SERVERS_AUTH) is None

    def test_shape_matches_the_nsflow_contract(self):
        """properties.http_headers.{properties,required} is what nsflow reads."""
        schema = AgentNetworkAssembler.build_mcp_sly_data_schema(NETWORK_DEF, MCP_SERVERS_AUTH)

        assert schema["type"] == "object"
        assert schema["required"] == ["http_headers"]
        http_headers = schema["properties"]["http_headers"]
        assert http_headers["type"] == "object"
        # Every USED url is declared (opportunistic injection)...
        assert sorted(http_headers["properties"]) == sorted([OAUTH_URL, FILE_AUTH_URL])
        # ...and each declared url expects an Authorization header.
        for url_schema in http_headers["properties"].values():
            assert url_schema["required"] == ["Authorization"]
            assert url_schema["properties"]["Authorization"]["type"] == "string"

    def test_required_is_the_headerless_subset_of_used_urls(self):
        """Only servers needing a client token gate chat; file-auth ones do not."""
        schema = AgentNetworkAssembler.build_mcp_sly_data_schema(NETWORK_DEF, MCP_SERVERS_AUTH)
        assert schema["properties"]["http_headers"]["required"] == [OAUTH_URL]

    def test_required_is_emitted_even_when_empty(self):
        """Omitting `required` makes nsflow gate every declared URL; [] must be explicit."""
        network_def = {"front_man": {"instructions": "Go.", "tools": [FILE_AUTH_URL]}}
        schema = AgentNetworkAssembler.build_mcp_sly_data_schema(network_def, MCP_SERVERS_AUTH)
        assert schema["properties"]["http_headers"]["required"] == []

    def test_unused_servers_are_not_declared(self):
        """Only URLs the network references appear in the schema."""
        schema = AgentNetworkAssembler.build_mcp_sly_data_schema(NETWORK_DEF, MCP_SERVERS_AUTH)
        assert UNUSED_URL not in schema["properties"]["http_headers"]["properties"]

    def test_duplicate_and_malformed_tools_entries_are_tolerated(self):
        """A URL used twice is declared once; non-str/None entries are skipped."""
        network_def = {
            "front_man": {"instructions": "Go.", "tools": [OAUTH_URL, "helper", None, 42]},
            "helper": {"instructions": "Help.", "tools": [OAUTH_URL]},
            "broken": "not-a-dict",
        }
        schema = AgentNetworkAssembler.build_mcp_sly_data_schema(network_def, MCP_SERVERS_AUTH)
        assert list(schema["properties"]["http_headers"]["properties"]) == [OAUTH_URL]
        assert schema["properties"]["http_headers"]["required"] == [OAUTH_URL]
