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

import asyncio
import json
import logging
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool
from neuro_san.internals.graph.activations.branch_activation import BranchActivation

from coded_tools.agent_network_editor.and_logger import AndLogger
from coded_tools.agent_network_editor.constants import AGENT_NETWORK_DEFINITION
from coded_tools.agent_network_editor.progress_handler import ProgressHandler
from neuro_san_studio.coded_tools.coded_tool_agent_caller import CodedToolAgentCaller


# pylint: disable=too-many-ancestors
class WriteAllInstructions(BranchActivation, CodedTool):
    """
    CodedTool that fans out per-agent instruction writing in parallel.

    The instructions_editor agent invokes this tool ONCE per request with:
      - agent_network_description (shared network-wide context, sent once)
      - agents: [{"agent_name": "...", "change_request": "..."}, ...]

    The tool dispatches one `instructions_writer` invocation per entry concurrently via
    asyncio.gather(). Each writer is a single LLM turn that answers with a JSON object
    ({"instructions": ..., "description": ...}); THIS tool parses that answer and writes
    the fields into sly_data's agent_network_definition itself. The writer has no tools
    of its own, so each agent costs exactly one model call — the earlier design's
    setter-tool round trip and closing confirmation turn are gone, and the writer can
    no longer misroute a field to the wrong agent, because the agent_name the fields
    are applied to is pinned here rather than re-stated by the model.

    Note that we doubly-inherit from BranchActivation to access the framework hook
    `use_tool()` that lets a CodedTool call other agents (in the same network or not).
    The actual call is wrapped via CodedToolAgentCaller.
    """

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> str:
        """
        Fan out one `instructions_writer` invocation per entry in `args["agents"]`,
        running them concurrently via asyncio.gather(), and apply each writer's
        JSON answer to the agent_network_definition as it completes.

        :param args: Tool arguments. Expected keys:
            - "agents": list of {"agent_name": str, "change_request": str (optional)}.
            - "agent_network_description": shared network-wide context, sent once and
              applied to every entry.
            - "tools": optional mapping with "instructions_writer" -> agent name to
              dispatch to (defaults to "instructions_writer").
        :param sly_data: Shared private data dictionary forwarded unchanged to each
            writer call (carries the `agent_network_definition` the fields are
            written into).
        :return: A success summary string if all writers succeeded, or an "Error: ..."
            string listing per-agent failures otherwise.
        """
        agents: list[dict[str, Any]] = args.get("agents") or []
        if not agents:
            return "Error: No agents provided."
        if not sly_data.get(AGENT_NETWORK_DEFINITION):
            return "Error: No network in sly data!"

        # Resolve the writer agent name via args.tools so hocon controls connectivity.
        tools_map: dict[str, str] = args.get("tools") or {}
        writer_name: str = tools_map.get("instructions_writer", "instructions_writer")

        logger = AndLogger(logging.getLogger(self.__class__.__name__))
        logger.info("Dispatching %d parallel '%s' calls", len(agents), writer_name)

        tasks = []
        for entry in agents:
            tasks.append(self.call_writer(writer_name, entry, args, sly_data))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ok: list[str] = []
        errs: list[str] = []
        for entry, result in zip(agents, results):
            name = entry.get("agent_name") or "<unknown>"
            if isinstance(result, BaseException):
                errs.append(f"{name}: {result!r}")
            elif result:
                # call_writer returns "" on success, or an "Error: ..." string.
                errs.append(f"{name}: {result}")
            else:
                ok.append(name)

        if errs:
            return f"Error: Instructions/description set for {len(ok)} agents; {len(errs)} failed: " + "; ".join(errs)
        return f"Instructions/description have been set for all {len(ok)} agents."

    async def call_writer(
        self,
        writer_name: str,
        entry: dict[str, Any],
        args: dict[str, Any],
        sly_data: dict[str, Any],
    ) -> str:
        """
        Invoke `instructions_writer` once for a single agent entry and apply its
        JSON answer to the network definition. Applying here — inside the
        gathered task, rather than after the whole gather — lets early writers'
        results reach the (throttled) progress stream while slower writers are
        still running, matching the incremental progress the setter tools used
        to produce.

        :param writer_name: The downstream agent name to dispatch to (typically
            "instructions_writer", resolved from `args.tools`).
        :param entry: One element of the `agents` list, e.g.
            {"agent_name": "...", "change_request": "..."}. `change_request` is
            optional and forwarded only when present.
        :param args: This tool's own args — carries the shared
            agent_network_description (forwarded only when non-empty) and the
            progress_reporter used for the per-agent progress report.
        :param sly_data: Shared private data forwarded to the writer call.
        :return: "" on success, or an "Error: ..." string describing the failure.
            A `ValueError` is raised if `entry` has no `agent_name`.
        """
        agent_name: str = entry.get("agent_name")
        if not agent_name:
            raise ValueError("Missing 'agent_name' in agents entry.")

        tool_args: dict[str, Any] = {"agent_name": agent_name}
        agent_network_description: str = args.get("agent_network_description") or ""
        if agent_network_description:
            tool_args["agent_network_description"] = agent_network_description
        change_request = entry.get("change_request")
        if change_request:
            tool_args["change_request"] = change_request

        caller = CodedToolAgentCaller(self, parsing=None, name=writer_name)
        response: str = await caller.call_agent(tool_args=tool_args, sly_data=sly_data)

        if isinstance(response, str) and response.lstrip().startswith("Error:"):
            # The writer itself failed loudly; pass its message through untouched.
            return response.strip()

        error: str = self._apply_writer_response(agent_name, response, sly_data)
        if error:
            return error

        await ProgressHandler.report_progress(args, sly_data, sly_data.get(AGENT_NETWORK_DEFINITION))
        return ""

    @staticmethod
    def _apply_writer_response(agent_name: str, response: str, sly_data: dict[str, Any]) -> str:
        """
        Parse one writer's JSON answer and write its fields into the
        agent_network_definition — the apply logic that previously lived in the
        set_agent_instructions/set_agent_description setter tools, minus the
        model round trips that drove them.

        Must stay synchronous (no awaits): the N concurrent writers share this
        sly_data without a lock, and what makes that safe is that this method
        runs start-to-finish in one step of the session's event loop, so
        applies can never interleave. (Writers also touch disjoint agent
        entries, but don't lean on that alone.)

        :param agent_name: The agent whose fields are being written. Pinned by
            the caller (not read back from the model's output), so a writer
            cannot misroute fields to another agent.
        :param response: The writer's response text; expected to be (or to
            contain) a JSON object with optional "instructions" and
            "description" string fields. A field absent from the object keeps
            its current value — the writer omits a field when a single-field
            change_request leaves the other unchanged, instead of re-emitting
            the existing text through the model.
        :param sly_data: Carries the agent_network_definition to update.
        :return: "" on success, or an "Error: ..." string.
        """
        network_def: dict[str, Any] = sly_data.get(AGENT_NETWORK_DEFINITION)
        if not network_def:
            return "Error: No network in sly data!"
        if agent_name not in network_def:
            return f"Error: Agent not found: {agent_name}"
        if network_def[agent_name].get("instructions") is None:
            return f"Error: Agent has no instructions field: {agent_name}. It is a function agent."

        fields: dict[str, Any] | None = WriteAllInstructions._parse_writer_fields(response)
        if fields is None:
            return f"Error: Writer response was not a JSON object: {response[:200]!r}"

        logger = AndLogger(logging.getLogger(WriteAllInstructions.__name__))
        applied = False
        for field in ("instructions", "description"):
            value = fields.get(field)
            if isinstance(value, str) and value:
                network_def[agent_name][field] = value
                logger.info("Set %s for '%s' (%d chars)", field, agent_name, len(value))
                applied = True
        if not applied:
            return "Error: Writer response contained neither 'instructions' nor 'description'."

        sly_data[AGENT_NETWORK_DEFINITION] = network_def
        return ""

    @staticmethod
    def _parse_writer_fields(response: str) -> dict[str, Any] | None:
        """
        Best-effort parse of a writer's answer into a dict.

        The writer is instructed to answer with ONLY a bare JSON object, but
        models occasionally wrap it in code fences or a sentence of prose, so
        on a failed direct parse this falls back to slicing from the first
        '{' to the last '}' before giving up.

        :param response: The writer's response text.
        :return: The parsed dict, or None when no JSON object can be extracted.
        """
        if not isinstance(response, str):
            return None
        text = response.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None
