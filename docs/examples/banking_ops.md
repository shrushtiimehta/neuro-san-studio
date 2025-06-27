#Banking Operations & Compliance Assistant

The **Banking Operations & Compliance Assistant** is a hierarchical structured multi-agent system designed to simulate a 
complete banking customer support organization.  full-service banking helpdesk 
with coverage for customer account management, fraud investigation, personal and business loans, wealth management, and investment advisory services.


---

## File

[banking_ops_aaosa.hocon](../../registries/banking_ops_aaosa.hocon)

---

## Description

This network organizes its intelligence into nested layers, with specialized agents collaborating to resolve customer inquiries. A central **Customer Service Representative** receives and parses incoming questions, dispatches relevant portions to subject matter agents, and collates the final output for the end user.

- **Task Routing by Expertise**: Each agent is domain-specific and may offload subtasks to its own subordinate agents, mirroring how departments operate in an actual bank.
- **Unified Conversational Front**: Despite its internal complexity, the system presents a single, coherent voice to the customer through its top-level representative.
- **Interactive Follow-ups**: Agents may request additional user input before responding, using clearly formatted, human-friendly prompts.
- **Expandable Structure**: Adding new banking functions (e.g., insurance, tax advisory) is as simple as plugging in new agents and updating tool references.

---

## Example Conversation

### Human

```text
I’m planning to invest $5,000 every month for the next 12 months. Can you suggest a strategy for this investment, including options suited for my risk
profile (low, moderate, or high)? Additionally, could you provide guidelines on how to avoid investment fraud and identify red flags?
```

### AI (Airline Policy 360 Assistant)

```text
You can carry your guitar as a cabin item on your flight to Madrid under the following conditions:

1. **Carry-On Baggage Policy**: Your guitar can be considered a cabin item if it fits within the carry-on size limits, which
are 9 in x 14 in x 22 in (23 cm x 35 cm x 56 cm). If the guitar exceeds these dimensions, it may need to be gate-checked,
especially if the overhead space is limited. For detailed information, visit the [Carry On Baggage page](https://www.united.com/en/us/fly/baggage/carry-on-bags.html).

2. **Special Items Policy**: Musical instruments like guitars can be carried as cabin baggage if they meet the size and
weight restrictions. They should fit in the overhead bin or under the seat. For more details, visit the [Special Items section](https://www.tsa.gov/travel/security-screening/whatcanibring/sporting-and-camping).

3. **Basic Economy Considerations**: If you're flying under a Basic Economy fare, carry-on bags are generally not included
unless you're on specific international routes. Ensure the guitar fits the dimensions allowed for a personal item or carry-on.
Otherwise, it will need to be checked in, possibly incurring additional fees. For more information, check the
[Basic Economy Restrictions](https://www.united.com/en/us/fly/travel/inflight/basic-economy.html).

Please ensure your guitar fits within the specified dimensions and policies to avoid any issues during your travel.
```

---

## Architecture Overview

### Frontman Agent: **Customer Service Representative**

- Acts as the entry point for all customer support requests.
- Determines which sub-agents need to respond based on the inquiry.
- Gathers and compiles final responses from sub-agents.
- Handles day-to-day support for banking products such as checking accounts, fraud detection, loans, and credit cards.

### Primary Domains (Tools called by the Frontman)

1. **Account Manager**
   - Manages customer relationships and resolves account-related inquiries.
   - Delegates to:
     - `Relationship Manager`
     - `Wealth Management Advisor`
     - `Investment Specialist`
     - `Trading Desk`
     - `Portfolio Manager`

2. **Fraud Prevention Specialist**
   - Identifies and investigates potential fraudulent activities on customer accounts. 
   - Delegates to:
     - `Fraud Investigation Team`
     - `Security_Analyst`

3. **Loan Officer**
   - Assesses and approves loans based on financial and account history.
   - Delegates to:
     - `Underwriter`
     - `Mortgage Specialist`
     - `Business Banking Officer`

