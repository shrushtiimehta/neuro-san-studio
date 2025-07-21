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

import os
import json
import requests
import logging
from dotenv import load_dotenv

from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApolloPeopleSearch(CodedTool):
    def __init__(self):
        load_dotenv()  # Load environment variables from .env file
        self.APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
        logger.debug(f"APOLLO_API_KEY value: {'set' if self.APOLLO_API_KEY else 'not set'}")
        if not self.APOLLO_API_KEY:
            logger.error("APOLLO_API_KEY environment variable not set")
            raise ValueError("APOLLO_API_KEY environment variable not set")
        self.apollo_url = "https://api.apollo.io/api/v1/mixed_people/search"
        logger.info("ApolloPeopleSearch initialized")

    def building_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Default seniority list for senior positions
        default_seniorities = ["senior", "c_suite", "vp", "director", "manager", "executive", "head"]
        # Clean all list-based arguments to remove None values
        person_seniorities = [str(s) for s in args.get("person_seniorities", default_seniorities) if s is not None]
        if not person_seniorities:
            person_seniorities = default_seniorities
        logger.debug(f"Raw person_seniorities in building_args: {args.get('person_seniorities', [])}")
        logger.debug(f"Cleaned person_seniorities in building_args: {person_seniorities}")

        payload = {
            "q_keywords": args.get("q_organization_keyword"),  # Align q_keywords with q_organization_keyword
            "include_similar_titles": args.get("include_similar_titles", False),
            "person_titles": [str(t) for t in args.get("person_titles", []) if t is not None],
            "person_seniorities": person_seniorities,
            "person_departments": [str(d) for d in args.get("person_departments", []) if d is not None],
            "q_organization_keyword": args.get("q_organization_keyword"),
            "person_locations": [str(l) for l in args.get("person_locations", []) if l is not None],
            "organization_not_locations": [str(l) for l in args.get("organization_not_locations", []) if l is not None],
            "page": args.get("page", 1),
            "per_page": args.get("per_page", 80),
        }
        logger.debug(f"Raw input arguments in building_args: {args}")
        logger.debug(f"Constructed payload in building_args: {json.dumps(payload)}")
        return {k: v for k, v in payload.items() if v not in [None, [], {}]}

    def clean_response_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        drop_keys = [
            "breadcrumbs", "partial_results_only", "has_join", "disable_eu_prospecting",
            "partial_results_limit", "pagination", "contacts", "model_ids",
            "num_fetch_result", "derived_params"
        ]
        for key in drop_keys:
            data.pop(key, None)

        people = data.get("people", [])
        logger.debug(f"Raw API response people count: {len(people)}")
        for person in people:
            logger.debug(f"Person data: location={person.get('location', 'N/A')}, seniority={person.get('seniority', 'N/A')}, organization={person.get('organization', {}).get('name', 'N/A')}")
        filtered_people = [
            self.clean_person_entry(p) for p in people if p.get("linkedin_url")
        ]
        logger.debug(f"Filtered people count (with linkedin_url): {len(filtered_people)}")
        return filtered_people

    def clean_person_entry(self, person: Dict[str, Any]) -> Dict[str, Any]:
        person_fields_to_remove = {
            "id", "name", "email", "photo_url", "email_status", "organization_id",
            "intent_strength", "show_intent"
        }
        org_fields_to_remove = {
            "id", "website_url", "primary_phone", "languages", "alexa_ranking",
            "phone", "linkedin_uid", "founded_year", "publicly_traded_symbol",
            "logo_url", "primary_domain"
        }
        org_growth_prefix = "organization_headcount_"
        employment_fields_to_remove = {"_id", "organization_id", "id", "key"}

        for field in person_fields_to_remove:
            person.pop(field, None)

        org = person.get("organization", {})
        for field in org_fields_to_remove:
            org.pop(field, None)
        for key in list(org.keys()):
            if key.startswith(org_growth_prefix):
                del org[key]

        for job in person.get("employment_history", []):
            for field in employment_fields_to_remove:
                job.pop(field, None)

        return person

    def matches_all_filters(self, person: Dict[str, Any], args: Dict[str, Any]) -> bool:
        def match_field(value: str, targets: List[str]) -> bool:
            logger.debug(f"match_field targets before filtering: {targets}")
            if not targets:
                logger.debug("No targets provided, skipping filter")
                return True
            try:
                # Filter out None values and ensure all targets are strings
                valid_targets = [str(t) for t in targets if t is not None]
                if not valid_targets:
                    logger.debug("All targets were None, skipping filter")
                    return True
                logger.debug(f"Matching value: {value}, against targets: {valid_targets}")
                return any(t.lower() in value.lower() for t in valid_targets)
            except AttributeError as e:
                logger.error(f"AttributeError in match_field: {str(e)}, value={value}, targets={targets}")
                return False

        logger.debug(f"Arguments received in matches_all_filters: {args}")
        # Check seniority
        if not match_field(person.get("seniority", ""), args.get("person_seniorities", [])):
            logger.debug(f"Filtered out due to seniority mismatch: {person.get('seniority', 'N/A')}")
            return False

        # Check organization name
        org_name = person.get("organization", {}).get("name", "").lower()
        if args.get("q_organization_keyword") and args["q_organization_keyword"].lower() not in org_name:
            logger.debug(f"Filtered out due to organization mismatch: {org_name}")
            return False

        # Extract country from person location
        person_location = person.get("location", "").lower()
        person_country = person_location.split(",")[-1].strip() if person_location and "," in person_location else person_location
        if args.get("person_locations"):
            normalized_locations = [str(loc).lower() for loc in args.get("person_locations", []) if loc is not None]
            if not person_country:
                logger.warning(f"Person has no location data: {person.get('linkedin_url', 'N/A')}")
                return False
            if not any(loc.lower() == person_country for loc in normalized_locations):
                logger.debug(f"Person filtered out due to country mismatch: {person_country}")
                return False

        # Extract country from organization location
        org_location = person.get("organization", {}).get("location", "").lower()
        org_country = org_location.split(",")[-1].strip() if org_location and "," in org_location else org_location
        if args.get("organization_not_locations") and any(loc.lower() == org_country for loc in args.get ("organization_not_locations", []) if loc is not None):
            logger.debug(f"Filtered out due to organization not country: {org_country}")
            return False

        return True

    def invoke(self, arguments: Dict[str, Any], sly_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.debug(f"Raw arguments received in invoke: {arguments}")
        payload = self.building_args(arguments)
        logger.info("Payload for Apollo People Search: %s", json.dumps(payload))
        headers = {
            "accept": "application/json",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "x-api-key": self.APOLLO_API_KEY
        }

        try:
            response = requests.post(self.apollo_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info("data received from Apollo API: %s", json.dumps(data, indent=2))
            logger.debug(f"Full API response: {json.dumps(data, indent=2)}")

            cleaned_people = self.clean_response_data(data)
            filtered_people = [
                p for p in cleaned_people if self.matches_all_filters(p, arguments)
            ]
            logger.debug(f"Final filtered people count: {len(filtered_people)}")

            data["people"] = filtered_people
            logger.info("Returning filtered data: %s", json.dumps(data))
            return data

        except requests.exceptions.RequestException as e:
            logger.error("Apollo API request failed: %s", str(e))
            return {"error": str(e)}

    async def async_invoke(self, arguments: Dict[str, Any], sly_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.invoke(arguments, sly_data)