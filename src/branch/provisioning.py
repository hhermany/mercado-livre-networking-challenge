import os

import requests
from dotenv import load_dotenv

from src.branch.addressing import build_branch_plan

load_dotenv(".env")


class BranchProvisioner:
    def __init__(self):
        self.base = os.environ["NAUTOBOT_URL"].rstrip("/")
        self.token = os.environ["NAUTOBOT_TOKEN"]
        self.headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
        }

    def _get(self, path, params=None):
        r = requests.get(
            f"{self.base}{path}",
            headers=self.headers,
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def _create_prefix(self, prefix, description):
        results = self._get(
            "/api/ipam/prefixes/",
            {"prefix": prefix},
        )["results"]

        exact = [p for p in results if p["prefix"] == prefix]

        if exact:
            raise ValueError(f"Prefix already exists: {prefix}")

        namespaces = self._get("/api/ipam/namespaces/")["results"]
        statuses = self._get(
            "/api/extras/statuses/",
            {"name": "Active"},
        )["results"]

        payload = {
            "prefix": prefix,
            "namespace": namespaces[0]["id"],
            "status": statuses[0]["id"],
            "description": description,
        }

        r = requests.post(
            f"{self.base}/api/ipam/prefixes/",
            headers=self.headers,
            json=payload,
            timeout=10,
        )
        r.raise_for_status()

        return r.json()

    def provision(self, branch_id):
        plan = build_branch_plan(branch_id)

        resources = [
            (plan.lan_prefix, f"{plan.name} LAN"),
            (plan.loopback_prefix, f"{plan.name} LO-MGMT"),
            (plan.vpn1_prefix, f"{plan.name} VPN1"),
            (plan.vpn2_prefix, f"{plan.name} VPN2"),
        ]

        created = []

        try:
            for prefix, description in resources:
                obj = self._create_prefix(prefix, description)
                created.append(obj)

        except Exception:
            for obj in reversed(created):
                requests.delete(
                    f"{self.base}/api/ipam/prefixes/{obj['id']}/",
                    headers=self.headers,
                    timeout=10,
                )
            raise

        return plan
