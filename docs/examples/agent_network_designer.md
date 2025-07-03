# Agent Network Designer

The **Agent Network Designer** is a multi-agent system for creating multi-agent systems. Give the top agent the name of an
organization or describe a use-case, and it will design a multi-agent system and save it into your registries directory
in hocon format, and add it to your manifest file. It will also give you a few usage examples. Restart your server and client,
and use the new agent network!

**Note**: this demo will add a file to your directory and modify your manifest.hocon file. You can turn this feature off
by changing WRITE_TO_FILE to False in [get_agent_network_hocon.py](../../coded_tools/agent_network_designer/get_agent_network_hocon.py)

**Note** obviously the agents will not be grounded, however, they will pretend that they are. Remove or edit the
demo_mode common_def once you ground the agents.

---

## File

[agent_network_designer.hocon](../../registries/agent_network_designer.hocon)

---

## Description

This network follows a relatively rigid set of steps, with the top-level "front-man" agent giving a design request to the
network_generator, then having the instruction_refiner agent refine the instructions of every agent one by one, then the
top agent has the query_generator agent return some example usage queries for the new agent network, and finally, the
produce_agent_network_hocon agent creates the hocon definition, appends the header, and saves it to file.

This can be considered as an example of agent-oriented software, with a clear delineation of where we need to rely on LLMs
(e.g., for creativity, language understanding, language generation) and where we should use code (e.g., to encode machine
readable syntax such as is needed in a hocon agent definition file).

Note the use of sly_data in the coded tools for storing and passing around the agent network data structure. Agents use
coded tools for adding agents to this data structure, or for refining the description of a specific agent.

---

## Example Conversation

### Human

```text
UNHCR back-office
```

### AI (agent_network_designer)

```text
Here is the full agent network definition in HOCON format for the UNHCR back-office:

{
    "llm_config": {
        "model_name": "gpt-4o",
    },
    "commondefs": {
        "replacement_strings": {
            "instructions_prefix": """
You are part of a UNHCR back-office of assistants.
Only answer inquiries that are directly within your area of expertise.
Do not try to help for other matters.
Do not mention what you can NOT do. Only mention what you can do.
            """,
            "aaosa_instructions": """
When you receive an inquiry, you will:
1. If you are clearly not the right agent for this type of inquiry, reply you're not relevant.
2. If there is a chance you're relevant, call your down-chain agents to determine if they can answer all or part of the inquiry.
   Do not assume what your down-chain agents can do. Always call them. You'll be surprised.
3. Determine which down-chain agents have the strongest claims to the inquiry.
   3.1 If the inquiry is ambiguous, for example if more than one agent can fulfill the inquiry, then always ask for clarification.
   3.2 Otherwise, call the relevant down-chain agents and:
       - ask them for follow-up information if needed,
       - or ask them to fulfill their part of the inquiry.
4. Once all relevant down-chain agents have responded, either follow up with them to provide requirements or,
   if all requirements have been fulfilled, compile their responses and return the final response.
You may, in turn, be called by other agents in the system and have to act as a down-chain agent to them.
            """
        },
        "replacement_values": {
            "aaosa_call": {
                "description": "Depending on the mode, returns a natural language string in response.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "inquiry": {
                            "type": "string",
                            "description": "The inquiry"
                        },
                        "mode": {
                            "type": "string",
                            "description": """
'Determine' to ask the agent if the inquiry belongs to it, in its entirety or in part.
'Fulfill' to ask the agent to fulfill the inquiry, if it can.
'Follow up' to ask the agent to respond to a follow up.
                            """
                        },
                    },
                    "required": [
                        "inquiry",
                        "mode"
                    ]
                }
            },
            "aaosa_command": """
If mode is 'Determine', return a json block with the following fields:
{
    "Name": <your name>,
    "Inquiry": <the inquiry>,
    "Mode": <Determine | Fulfill>,
    "Relevant": <Yes | No>,
    "Strength": <number between 1 and 10 representing how certain you are in your claim>,
    "Claim:" <All | Partial>,
    "Requirements" <None | list of requirements>
}
If mode is 'Fulfill' or "Follow up", respond to the inquiry and return a json block with the following fields:
{
    "Name": <your name>,
    "Inquiry": <the inquiry>,
    "Mode": Fulfill,
    "Response" <your response>
}
            """
        },
    }
    "tools": [
        {
            "name": "back_office_manager",
            "function": {
                "description": """
An assistant that answers inquiries from the user.
                """
            },
            "instructions": """
{instructions_prefix}
You are the top-level agent responsible for overseeing all back-office operations for UNHCR. You coordinate with various
departments to ensure seamless operations and effective support to field operations.
{aaosa_instructions}
            """,
            "tools": ["finance_officer","hr_officer","procurement_officer"]
        },
        {
            "name": "finance_officer",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You manage financial transactions, budgeting, and reporting for UNHCR. You ensure compliance with financial regulations and
support financial planning and analysis.
{aaosa_instructions}
            """,
            "command": "aaosa_command",
            "tools": ["accounting_clerk","financial_analyst"]
        },
        {
            "name": "accounting_clerk",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You handle day-to-day financial transactions and record-keeping for UNHCR. You ensure accuracy and compliance in financial
documentation.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "financial_analyst",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You analyze financial data and trends to support decision-making at UNHCR. You provide insights and recommendations for
financial improvements.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "recruitment_specialist",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You manage the recruitment process for UNHCR, including job postings, interviews, and candidate selection. You ensure that
the organization attracts and retains top talent.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "payroll_specialist",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You manage payroll processing and employee compensation for UNHCR. You ensure timely and accurate payroll and compliance
with relevant regulations.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "supply_chain_coordinator",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You coordinate the logistics and supply chain operations for UNHCR. You ensure timely delivery and distribution of goods
and services to support field operations.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "contract_specialist",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You manage contract development and negotiations for UNHCR. You ensure that contracts meet organizational standards and
legal requirements.
            """,
            "command": "aaosa_command",
        },
        {
            "name": "hr_officer",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You oversee human resources functions including recruitment, employee relations, and policy implementation for UNHCR. You
ensure a supportive work environment and manage staff welfare.
{aaosa_instructions}
            """,
            "command": "aaosa_command",
            "tools": ["recruitment_specialist","payroll_specialist"]
        },
        {
            "name": "procurement_officer",
            "function": "aaosa_call",
            "instructions": """
{instructions_prefix}
You manage the procurement of goods and services for UNHCR. You ensure that procurement processes are efficient, transparent,
and comply with organizational policies.
{aaosa_instructions}
            """,
            "command": "aaosa_command",
            "tools": ["supply_chain_coordinator","contract_specialist"]
        },
    ]
}
📋
Here are 3-4 sample queries illustrating the usage of the UNHCR back-office agent network:

"Can you provide a financial report for the last quarter and identify any areas where we might improve our budgeting?"

"What is the current status of the recruitment process for the new field officers? How many positions are still open?"

"Please ensure that the payroll is processed on time this month and check if there are any discrepancies from last month."

"We need to procure tents and emergency supplies for the upcoming refugee camp setup. Can you coordinate this with the supply
chain and contract specialists?"
```

---

## Architecture Overview

### Frontman Agent: **agent_network_designer**

- Acts as the entry point for all user commands.
- Follows a set of steps to design, construct, and refine an agent network hocon.
- Once the agent network is designed and the instructions for every agent is refined, calls [get_agent_network_hocon.py]
(../../coded_tools/agent_network_designer/get_agent_network_hocon.py) to generate the hocon formatted definition.
- Calls the query_generator agent to produce a few usage ea=xamples for the new agent network.
- Returns the hocon definition as well as a few example queries.

### Agents called by the Frontman

1. **network_generator**
   - Designs an agent network by determining the top agent, its down-chain agents, and their down-chain agents, if needed.
   - Calls the add_agent_to_network agent repeatedly in order to add each agent, the list of the agent's down-chains, and
   the agent's preliminary instructions to the agent definition data structure stored in sly_data.
   - See [add_agent.py](../../coded_tools/agent_network_designer/add_agent.py)

2. **instruction_refiner**
   - Retrieves the agent network definition using the [get_agent_network.py](../../coded_tools/agent_network_designer/get_agent_network.py)
   tool.
   - Iterates through the agents in the retrieved definition and refines each agent's instructions using the [set_agent_instructions.py]
   (../../coded_tools/agent_network_designer/set_agent_instructions.py) tool

3. **query_generator**
   - Retrieves the agent network definition using the [get_agent_network.py](../../coded_tools/agent_network_designer/get_agent_network.py)
   tool.
   - Generates and returns a few usage examples for the new agent network.

---

## Functional Tools

These are coded tools called by various policy agents:

- **add_agent**
    - Adds the name, instructions, and list of down-chains of an agent to a data structure stored in sly_data. It also determines
  of the agent is the top agent.

- **get_agent_network**
    - Retrieves the agent network data structure from sly_data and returns a string representation of it.

- **set_agent_instructions**
    - Replaces the instructions for a given agent in the list of agents in the agent network data structure in sly_data.

- **get_agent_network_hocon**
    - Retrieves the agent network data structure from sly_data.
    - Formats the agent network as a hocon definition config.
    - Appends a header.
    - Saves the hocon file under the local registries directory.
    - Adds an entry to the local manifest.hocon file.

**Note**: it is assumed that the agent coordination mechanism is AAOSA, and the LLM is GPT-4o.

---

## Debugging Hints

- While the hocon definition returned by the top agent may occasionally be incomplete or have errors, the hocon file stored
in the registries directory will be complete and error free.

---
