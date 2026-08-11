import os

import requests
from dotenv import load_dotenv

from src.ipam.base import IPAMProvider

load_dotenv()


class NautobotIPAMProvider(IPAMProvider):
    """IPAM provider backed by the Nautobot REST API."""

    def __init__(self) -> None:
        self.base_url = os.getenv("NAUTOBOT_URL")
        self.token = os.getenv("NAUTOBOT_TOKEN")
        self.parent_prefix = os.getenv("NAUTOBOT_PARENT_PREFIX")

        if not all((self.base_url, self.token, self.parent_prefix)):
            raise ValueError("Missing required Nautobot environment variables.")

        self.headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def allocate_prefix(self, prefix_length: int, description: str) -> dict:
        """Allocate the next available child prefix from the parent pool."""

        parent_id = self._get_parent_prefix_id()

        url = (
            f"{self.base_url}/api/ipam/prefixes/"
            f"{parent_id}/available-prefixes/"
        )

        payload = {
            "prefix_length": prefix_length,
            "status": "Active",
            "description": description,
        }

        response = requests.post(
            url,
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

        return response.json()

    def release_prefix(self, prefix_id: str) -> None:
        """Delete a previously allocated prefix."""

        url = f"{self.base_url}/api/ipam/prefixes/{prefix_id}/"

        response = requests.delete(
            url,
            headers=self.headers,
            timeout=10,
        )
        response.raise_for_status()

    def _get_parent_prefix_id(self) -> str:
        """Return the Nautobot object ID for the configured parent prefix."""

        url = f"{self.base_url}/api/ipam/prefixes/"

        response = requests.get(
            url,
            headers=self.headers,
            params={"prefix": self.parent_prefix},
            timeout=10,
        )
        response.raise_for_status()

        results = response.json()["results"]

        if len(results) != 1:
            raise ValueError(
                f"Expected exactly one parent prefix: {self.parent_prefix}"
            )

        return results[0]["id"]
