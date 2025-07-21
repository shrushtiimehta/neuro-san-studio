import requests
import os
import logging
from typing import Dict, Any

from neuro_san.interfaces.coded_tool import CodedTool

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ApolloCompanySearch(CodedTool):
    def __init__(self):
        self.APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
        if not self.APOLLO_API_KEY:
            logger.error("APOLLO_API_KEY environment variable not set")
        self.apollo_url = "https://api.apollo.io/api/v1/organizations/search"
        logger.info("ApolloCompanySearch initialized")

    def building_args(self, args: Dict[str, Any]) -> Any:
        payload = {
            "q_organization_keyword": args.get("q_organization_keyword"),
            "organization_num_employees_ranges": args.get("organization_num_employees_ranges", []),
            "organization_locations": args.get("organization_locations", []),
            "organization_not_locations": args.get("organization_not_locations", []),
            "q_organization_keyword_tags": args.get("q_organization_keyword_tags", []),
            "page": args.get("page", 1),
            "per_page": args.get("per_page", 100),
            "organization_city": args.get("organization_city", []),
            "organization_state": args.get("organization_state", []),
        }

        if args.get("revenue_range_min") or args.get("revenue_range_max"):
            payload["revenue_range"] = {
                "min": args.get("revenue_range_min"),
                "max": args.get("revenue_range_max")
            }

        if args.get("latest_funding_amount_range_min") or args.get("latest_funding_amount_range_max"):
            payload["latest_funding_amount_range"] = {
                "min": args.get("latest_funding_amount_range_min"),
                "max": args.get("latest_funding_amount_range_max")
            }

        if args.get("total_funding_range_min") or args.get("total_funding_range_max"):
            payload["total_funding_range"] = {
                "min": args.get("total_funding_range_min"),
                "max": args.get("total_funding_range_max")
            }

        if args.get("latest_funding_date_range_min") or args.get("latest_funding_date_range_max"):
            payload["latest_funding_date_range"] = {
                "min": args.get("latest_funding_date_range_min"),
                "max": args.get("latest_funding_date_range_max")
            }

        payload = {k: v for k, v in payload.items() if v not in [None, [], {}]}
        return payload

    def invoke(self, arguments: Dict[str, Any], sly_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = self.building_args(arguments)
        headers = {
            "accept": "application/json",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
            "x-api-key": self.APOLLO_API_KEY
        }
        try:
            response = requests.post(self.apollo_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error("Request error: %s", str(e))
            return {"error": str(e)}

    async def async_invoke(self, arguments: Dict[str, Any], sly_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.invoke(arguments, sly_data)
        