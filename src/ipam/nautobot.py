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
        # Legacy/default pool: VPN overlay addressing.
        self.parent_prefix = os.getenv("NAUTOBOT_PARENT_PREFIX")
        self.pools = {
            "vpn": os.getenv("NAUTOBOT_VPN_POOL", self.parent_prefix),
            "lan": os.getenv("NAUTOBOT_LAN_POOL"),
            "loopback": os.getenv("NAUTOBOT_LOOPBACK_POOL"),
        }

        if not all((self.base_url, self.token, self.parent_prefix)):
            raise ValueError("Missing required Nautobot environment variables.")

        self.headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def allocate_prefix(
        self,
        prefix_length: int,
        description: str,
        pool: str = "vpn",
    ) -> dict:
        """Allocate the next available child prefix from a named pool."""

        if pool not in self.pools:
            raise ValueError(f"Unknown Nautobot pool: {pool}")

        parent_prefix = self.pools[pool]

        if not parent_prefix:
            raise ValueError(f"Nautobot pool is not configured: {pool}")

        parent_id = self._get_parent_prefix_id(parent_prefix)

        url = f"{self.base_url}/api/ipam/prefixes/{parent_id}/available-prefixes/"

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

    def _get_parent_prefix_id(self, parent_prefix: str | None = None) -> str:
        """Return the Nautobot object ID for a parent prefix."""

        parent_prefix = parent_prefix or self.parent_prefix

        url = f"{self.base_url}/api/ipam/prefixes/"

        response = requests.get(
            url,
            headers=self.headers,
            params={"prefix": parent_prefix},
            timeout=10,
        )
        response.raise_for_status()

        results = response.json()["results"]

        if len(results) != 1:
            raise ValueError(f"Expected exactly one parent prefix: {parent_prefix}")

        return results[0]["id"]
