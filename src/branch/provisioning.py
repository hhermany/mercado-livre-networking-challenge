import os

import requests
from dotenv import load_dotenv

from src.branch.addressing import (
    BranchPlan,
    build_branch_plan,
)
from src.branch.next_id import (
    get_next_branch_id,
)

load_dotenv(".env")


class BranchProvisioner:
    def __init__(self):
        self.base = os.environ["NAUTOBOT_URL"].rstrip("/")

        self.token = os.environ["NAUTOBOT_TOKEN"]

        self.headers = {
            "Authorization": (f"Token {self.token}"),
            "Content-Type": "application/json",
        }

    def _get(
        self,
        path,
        params=None,
    ):
        response = requests.get(
            f"{self.base}{path}",
            headers=self.headers,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def _create_prefix(
        self,
        prefix,
        description,
    ):
        results = self._get(
            "/api/ipam/prefixes/",
            {
                "prefix": prefix,
            },
        )["results"]

        exact = [item for item in results if item["prefix"] == prefix]

        if exact:
            raise ValueError(f"Prefix already exists: {prefix}")

        namespaces = self._get("/api/ipam/namespaces/")["results"]

        statuses = self._get(
            "/api/extras/statuses/",
            {
                "name": "Active",
            },
        )["results"]

        payload = {
            "prefix": prefix,
            "namespace": namespaces[0]["id"],
            "status": statuses[0]["id"],
            "description": description,
        }

        response = requests.post(
            (f"{self.base}/api/ipam/prefixes/"),
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def _delete_prefix_object(
        self,
        obj,
    ):
        response = requests.delete(
            (f"{self.base}/api/ipam/prefixes/{obj['id']}/"),
            headers=self.headers,
            timeout=10,
        )

        response.raise_for_status()

    def plan(
        self,
        branch_id=None,
    ) -> BranchPlan:
        """
        Monta o plano deterministico sem
        escrever no Nautobot.
        """

        if branch_id is None:
            branch_id = get_next_branch_id()

        return build_branch_plan(branch_id)

    @staticmethod
    def resources_for_plan(
        plan,
    ):
        return [
            (
                plan.lan_prefix,
                f"{plan.name} LAN",
            ),
            (
                plan.loopback_prefix,
                f"{plan.name} LO-MGMT",
            ),
            (
                plan.vpn1_prefix,
                f"{plan.name} VPN1",
            ),
            (
                plan.vpn2_prefix,
                f"{plan.name} VPN2",
            ),
        ]

    def reserve(
        self,
        branch_id=None,
    ):
        """
        Reserva exatamente os recursos de um
        Candidate.

        Retorna tambem os objetos Nautobot
        criados para permitir controle do
        lifecycle.
        """

        plan = self.plan(branch_id=branch_id)

        created = []

        try:
            for (
                prefix,
                description,
            ) in self.resources_for_plan(plan):
                created.append(
                    self._create_prefix(
                        prefix,
                        description,
                    )
                )

        except Exception:
            for obj in reversed(created):
                try:
                    self._delete_prefix_object(obj)
                except Exception:
                    pass

            raise

        return {
            "plan": plan,
            "objects": created,
        }

    def release(
        self,
        objects,
    ):
        errors = []

        for obj in reversed(list(objects)):
            try:
                self._delete_prefix_object(obj)
            except Exception as exc:
                errors.append(str(exc))

        if errors:
            raise RuntimeError(
                "Falha ao liberar recursos no Nautobot: " + "; ".join(errors)
            )

    def provision(
        self,
        branch_id=None,
    ) -> BranchPlan:
        """
        Compatibilidade com o fluxo existente.

        Reserva todos os recursos e retorna
        apenas o BranchPlan.
        """

        reservation = self.reserve(branch_id=branch_id)

        return reservation["plan"]
