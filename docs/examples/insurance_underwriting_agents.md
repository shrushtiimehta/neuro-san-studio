# Architecture Overview

## Frontman Agent: `insurance_agent`

- **Role**: Main entry point for all business insurance inquiries for **Hartford**.
- **Responsibilities**:
  - Interprets user commands.
  - Delegates to underwriting or claims processing agents.
  - Coordinates downstream agents to fulfill multi-step workflows.

---

## Agents Called by the Frontman

### `underwriting_decision_agent`

- **Purpose**: Manages underwriting operations.
- **Responsibilities**:
  - Collects and verifies submission data.
  - Analyzes third-party risk indicators.
  - Makes underwriting decisions.
- **Sub-agents**:
  - `insurance_broker_agent`
  - `third_party_data_review_agent`
  - `underwriter_analysis_agent`

---

### `claims_processing_agent`

- **Purpose**: Manages the entire claims lifecycle.
- **Responsibilities**:
  - Handles intake, investigation, and settlement.
  - Communicates with claimants and internal teams.
- **Sub-agents**:
  - `claims_intake_handler`
  - `claims_investigation_agent`
  - `claims_adjustment_agent`

---

## Agents Under Underwriting Branch

### `insurance_broker_agent`

- **Purpose**: Interfaces with brokers.
- **Responsibilities**:
  - Receives and categorizes submissions.
  - Coordinates feedback and missing info.
  - Delivers underwriting decisions.
- **Tools**:
  - `acord_application_handler`
  - `loss_analysis_handler`

#### `acord_application_handler`

- **Purpose**: Validates ACORD applications.
- **Responsibilities**:
  - Checks for completeness and consistency.
  - Flags missing or non-compliant data.

#### `loss_analysis_handler`

- **Purpose**: Reviews loss history.
- **Responsibilities**:
  - Identifies patterns and calculates loss ratios.
  - Flags high-risk indicators.

---

### `third_party_data_review_agent`

- **Purpose**: Collects and consolidates external risk data.
- **Responsibilities**:
  - Pulls building, environmental, and regulatory information.
  - Creates consolidated third-party data reports.
- **Tools**:
  - `building_characteristics_reviewer`
  - `risk_condition_reviewer`
  - `specific_segment_reports_reviewer`
  - `valuation_report_handler`
  - `ownership_verification_handler`

#### `building_characteristics_reviewer`

- Evaluates structure, fire safety, and electrical system.

#### `risk_condition_reviewer`

- Analyzes visual cues from maps/images for neighborhood and building risk.

#### `specific_segment_reports_reviewer`

- Reviews OSHA, bankruptcy, liens, and regulatory flags.

#### `valuation_report_handler`

- Computes property valuation based on sq ft and location-adjusted rates.

#### `ownership_verification_handler`

- Verifies property ownership, chain-of-title, and document authenticity.

---

### `underwriter_analysis_agent`

- **Purpose**: Synthesizes all underwriting data for final decision.
- **Responsibilities**:
  - Evaluates exposure, aggregation, and portfolio alignment.
- **Tools**:
  - `risk_exposure_analyzer`
  - `aggregation_checker`
  - `benchmarking_handler`

#### `risk_exposure_analyzer`

- Scores exposure to fire, flood, crime, and hazard proximity.

#### `aggregation_checker`

- Ensures risk does not overconcentrate Hartford’s portfolio.

#### `benchmarking_handler`

- Benchmarks case against portfolio trends, pricing, and losses.

---

## Agents Under Claims Branch

### `claims_intake_handler`

- **Purpose**: Manages initial claim intake.
- **Responsibilities**:
  - Verifies policy coverage.
  - Collects documents and assigns claim ID.

---

### `claims_investigation_agent`

- **Purpose**: Investigates claim validity.
- **Responsibilities**:
  - Interviews claimants and reviews third-party reports.
  - Coordinates site inspections.
- **Tools**:
  - `site_inspector`
  - `report_verification_handler`

#### `site_inspector`

- Performs on-site damage assessments and takes supporting evidence.

#### `report_verification_handler`

- Authenticates and validates third-party documents and reports.

---

### `claims_adjustment_agent`

- **Purpose**: Finalizes claim settlement.
- **Responsibilities**:
  - Applies policy limits and deductibles.
  - Issues settlement decision and coordinates payout.

---
