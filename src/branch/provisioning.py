import os
from ipaddress import ip_network

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
            "Authorization": f"Token {self.token}",
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

    def _post(
        self,
        path,
        payload,
    ):
        response = requests.post(
            f"{self.base}{path}",
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def _patch(
        self,
        path,
        object_id,
        payload,
    ):
        response = requests.patch(
            f"{self.base}{path}{object_id}/",
            headers=self.headers,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        return response.json()

    def _delete(
        self,
        path,
        object_id,
    ):
        response = requests.delete(
            f"{self.base}{path}{object_id}/",
            headers=self.headers,
            timeout=10,
        )

        response.raise_for_status()

    def _active_status_id(
        self,
        *,
        content_type=None,
    ):
        params = {
            "name": "Active",
        }

        if content_type:
            params["content_types"] = content_type

        results = self._get(
            "/api/extras/statuses/",
            params,
        )["results"]

        if not results:
            raise RuntimeError(
                f"Nautobot status Active not found for {content_type or 'object'}."
            )

        return results[0]["id"]

    def _namespace_id(self):
        results = self._get(
            "/api/ipam/namespaces/",
        )["results"]

        if not results:
            raise RuntimeError("No Nautobot namespace available.")

        return results[0]["id"]

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

        payload = {
            "prefix": prefix,
            "namespace": self._namespace_id(),
            "status": self._active_status_id(),
            "description": description,
        }

        return self._post(
            "/api/ipam/prefixes/",
            payload,
        )

    def _create_ip_address(
        self,
        address,
        description,
    ):
        results = self._get(
            "/api/ipam/ip-addresses/",
            {
                "address": address,
            },
        )["results"]

        exact = [item for item in results if item.get("address") == address]

        if exact:
            raise ValueError(f"IP address already exists: {address}")

        payload = {
            "address": address,
            "namespace": self._namespace_id(),
            "status": self._active_status_id(
                content_type="ipam.ipaddress",
            ),
            "description": description,
        }

        return self._post(
            "/api/ipam/ip-addresses/",
            payload,
        )

    def _create_vpn(
        self,
        name,
        description,
    ):
        results = self._get(
            "/api/vpn/vpns/",
            {
                "name": name,
            },
        )["results"]

        exact = [item for item in results if item.get("name") == name]

        if exact:
            raise ValueError(f"VPN already exists: {name}")

        return self._post(
            "/api/vpn/vpns/",
            {
                "name": name,
                "description": description,
            },
        )

    def _create_vpn_endpoint(
        self,
        *,
        source_ipaddress,
    ):
        return self._post(
            "/api/vpn/vpn-tunnel-endpoints/",
            {
                "source_ipaddress": source_ipaddress,
            },
        )

    def _create_vpn_tunnel(
        self,
        *,
        name,
        description,
        vpn_id,
        endpoint_a,
        endpoint_z,
    ):
        results = self._get(
            "/api/vpn/vpn-tunnels/",
            {
                "name": name,
            },
        )["results"]

        exact = [item for item in results if item.get("name") == name]

        if exact:
            raise ValueError(f"VPN tunnel already exists: {name}")

        payload = {
            "name": name,
            "description": description,
            "vpn": vpn_id,
            "endpoint_a": endpoint_a,
            "endpoint_z": endpoint_z,
            "status": self._active_status_id(
                content_type="vpn.vpntunnel",
            ),
        }

        return self._post(
            "/api/vpn/vpn-tunnels/",
            payload,
        )

    @staticmethod
    def _overlay_hosts(prefix):
        hosts = list(ip_network(prefix).hosts())

        if len(hosts) != 2:
            raise ValueError(f"VPN overlay must be /30: {prefix}")

        # Contrato do projeto:
        # primeiro usable = Palo Alto/DC
        # segundo usable = FortiGate/Branch.
        return str(hosts[0]), str(hosts[1])

    def _create_overlay_inventory(
        self,
        plan,
        tunnel_number,
        prefix,
    ):
        pa_ip, fg_ip = self._overlay_hosts(prefix)

        pa_address = self._create_ip_address(
            f"{pa_ip}/30",
            (f"{plan.name} VPN{tunnel_number} Palo Alto DC endpoint"),
        )

        fg_address = self._create_ip_address(
            f"{fg_ip}/30",
            (f"{plan.name} VPN{tunnel_number} FortiGate branch endpoint"),
        )

        vpn_name = f"{plan.name}-VPN{tunnel_number}"

        vpn = self._create_vpn(
            vpn_name,
            (f"VPN {tunnel_number} with {plan.name}"),
        )

        endpoint_pa = self._create_vpn_endpoint(
            source_ipaddress=pa_address["id"],
        )

        endpoint_fg = self._create_vpn_endpoint(
            source_ipaddress=fg_address["id"],
        )

        tunnel = self._create_vpn_tunnel(
            name=vpn_name,
            description=(f"VPN {tunnel_number} with {plan.name}"),
            vpn_id=vpn["id"],
            endpoint_a=endpoint_pa["id"],
            endpoint_z=endpoint_fg["id"],
        )

        return {
            "ip_addresses": [
                pa_address,
                fg_address,
            ],
            "vpns": [
                vpn,
            ],
            "vpn_endpoints": [
                endpoint_pa,
                endpoint_fg,
            ],
            "vpn_tunnels": [
                tunnel,
            ],
        }

    @staticmethod
    def _reference_id(value):
        if isinstance(value, dict):
            return value.get("id")

        return value

    def _exact_object(
        self,
        path,
        field,
        value,
    ):
        results = self._get(
            path,
            {
                field: value,
            },
        )["results"]

        exact = [item for item in results if item.get(field) == value]

        if len(exact) > 1:
            raise RuntimeError(f"Nautobot retornou objetos duplicados: {field}={value}")

        if not exact:
            return None

        return exact[0]

    def _load_existing_reservation(
        self,
        branch_id,
    ):
        """
        Procura uma reserva deterministica ja
        existente para a branch.

        Retorna None somente quando nenhum
        recurso da branch existe.

        Se encontrar reserva parcial ou
        inconsistente, falha de forma segura.
        """

        plan = self.plan(branch_id=branch_id)

        found = 0
        problems = []

        prefixes = []

        for prefix, description in self.resources_for_plan(plan):
            obj = self._exact_object(
                "/api/ipam/prefixes/",
                "prefix",
                prefix,
            )

            if obj is None:
                problems.append(f"prefix ausente: {prefix}")
                continue

            found += 1

            if obj.get("description") != description:
                problems.append(
                    f"prefix {prefix} pertence a '{obj.get('description')}'"
                )

            prefixes.append(obj)

        expected_ips = []

        for tunnel_number, prefix in (
            (1, plan.vpn1_prefix),
            (2, plan.vpn2_prefix),
        ):
            pa_ip, fg_ip = self._overlay_hosts(prefix)

            expected_ips.extend(
                (
                    (
                        f"{pa_ip}/30",
                        (f"{plan.name} VPN{tunnel_number} Palo Alto DC endpoint"),
                    ),
                    (
                        f"{fg_ip}/30",
                        (f"{plan.name} VPN{tunnel_number} FortiGate branch endpoint"),
                    ),
                )
            )

        ip_addresses = []

        for address, description in expected_ips:
            obj = self._exact_object(
                "/api/ipam/ip-addresses/",
                "address",
                address,
            )

            if obj is None:
                problems.append(f"IP ausente: {address}")
                continue

            found += 1

            if obj.get("description") != description:
                problems.append(
                    f"IP {address} possui descricao "
                    f"inesperada: '{obj.get('description')}'"
                )

            ip_addresses.append(obj)

        vpns = []

        for tunnel_number in (1, 2):
            name = f"{plan.name}-VPN{tunnel_number}"

            obj = self._exact_object(
                "/api/vpn/vpns/",
                "name",
                name,
            )

            if obj is None:
                problems.append(f"VPN ausente: {name}")
                continue

            found += 1
            vpns.append(obj)

        vpn_tunnels = []

        for tunnel_number in (1, 2):
            name = f"{plan.name}-VPN{tunnel_number}"

            obj = self._exact_object(
                "/api/vpn/vpn-tunnels/",
                "name",
                name,
            )

            if obj is None:
                problems.append(f"VPN tunnel ausente: {name}")
                continue

            found += 1
            vpn_tunnels.append(obj)

        # Se absolutamente nada da branch existe,
        # nao ha reserva a reutilizar.
        if found == 0:
            return None

        # Temos algum recurso. A partir daqui
        # exigimos a reserva completa.
        if problems:
            raise RuntimeError(
                "Reserva parcial/inconsistente no "
                "Nautobot para "
                f"{plan.name}: " + "; ".join(problems)
            )

        expected_ip_ids = {obj["id"] for obj in ip_addresses}

        all_endpoints = self._get(
            "/api/vpn/vpn-tunnel-endpoints/",
            {
                "limit": 500,
            },
        )["results"]

        vpn_endpoints = [
            obj
            for obj in all_endpoints
            if self._reference_id(obj.get("source_ipaddress")) in expected_ip_ids
        ]

        if len(vpn_endpoints) != 4:
            raise RuntimeError(
                "Reserva parcial/inconsistente no "
                f"Nautobot para {plan.name}: "
                "esperados 4 VPN endpoints, "
                f"encontrados {len(vpn_endpoints)}"
            )

        # Confirma que os dois tunnels referenciam
        # os quatro endpoints esperados.
        endpoint_ids = {obj["id"] for obj in vpn_endpoints}

        referenced_endpoint_ids = set()

        for tunnel in vpn_tunnels:
            referenced_endpoint_ids.add(self._reference_id(tunnel.get("endpoint_a")))
            referenced_endpoint_ids.add(self._reference_id(tunnel.get("endpoint_z")))

        referenced_endpoint_ids.discard(None)

        if referenced_endpoint_ids != endpoint_ids:
            raise RuntimeError(
                "Reserva parcial/inconsistente no "
                f"Nautobot para {plan.name}: "
                "VPN tunnels nao referenciam "
                "os quatro endpoints esperados."
            )

        objects = {
            "prefixes": prefixes,
            "ip_addresses": ip_addresses,
            "vpns": vpns,
            "vpn_endpoints": vpn_endpoints,
            "vpn_tunnels": vpn_tunnels,
        }

        objects["objects"] = list(objects["prefixes"])

        return {
            "plan": plan,
            "objects": objects,
            "created": False,
        }

    def ensure_reserved(
        self,
        branch_id=None,
    ):
        """
        Garante que a reserva exista.

        - reserva inexistente: cria;
        - reserva completa: reutiliza;
        - reserva parcial: bloqueia.
        """

        if branch_id is None:
            branch_id = get_next_branch_id()

        existing = self._load_existing_reservation(branch_id)

        if existing is not None:
            return existing

        reservation = self.reserve(branch_id=branch_id)

        reservation["created"] = True

        return reservation

    @staticmethod
    def _proposal_parts(proposal):
        encryption, integrity = proposal.lower().split("-", 1)

        encryption_map = {
            "des": "DES",
            "3des": "3DES",
            "aes128": "AES-128-CBC",
            "aes192": "AES-192-CBC",
            "aes256": "AES-256-CBC",
        }

        integrity_map = {
            "sha1": "SHA1",
            "sha256": "SHA256",
            "sha384": "SHA384",
            "sha512": "SHA512",
        }

        return (
            encryption_map.get(
                encryption,
                encryption.upper(),
            ),
            integrity_map.get(
                integrity,
                integrity.upper(),
            ),
        )

    def _get_or_create_named(
        self,
        path,
        name,
        payload,
    ):
        existing = self._exact_object(
            path,
            "name",
            name,
        )

        if existing is not None:
            return existing, False

        return (
            self._post(
                path,
                payload,
            ),
            True,
        )

    def enrich_reservation(
        self,
        reservation,
        *,
        vpn_metadata=None,
    ):
        """
        Enriquece a reserva basica com o mesmo
        nivel de inventario usado pela golden:

        - Phase1 Policy
        - Phase2 Policy
        - VPN Profile
        - crypto/lifetimes
        - identificacao PA/FG
        - PSK placeholders
        - IPsec-Tunnel
        - profile associado a VPNs/endpoints/tunnels

        Nao usa a API de assignments porque
        esta instalacao do Nautobot retorna
        HTTP 500 nesse endpoint.
        """

        plan = reservation["plan"]
        objects = reservation["objects"]

        metadata = {
            "ike_version": 2,
            "phase1_proposal": "des-sha256",
            "phase1_dh": 14,
            "phase1_lifetime": 28800,
            "phase2_proposal": "des-sha256",
            "phase2_pfs": 14,
            "phase2_lifetime": 3600,
        }

        if vpn_metadata:
            metadata.update(
                {key: value for key, value in vpn_metadata.items() if value is not None}
            )

        p1_enc, p1_integrity = self._proposal_parts(metadata["phase1_proposal"])

        p2_enc, p2_integrity = self._proposal_parts(metadata["phase2_proposal"])

        phase1_name = f"{plan.name}-PHASE1"

        phase2_name = f"{plan.name}-PHASE2"

        profile_name = f"{plan.name}-S2S"

        phase1, phase1_created = self._get_or_create_named(
            "/api/vpn/vpn-phase-1-policies/",
            phase1_name,
            {
                "name": phase1_name,
                "description": (
                    f"{plan.name} AUTO | "
                    f"{metadata['phase1_proposal']} | "
                    f"DH{metadata['phase1_dh']} | "
                    f"{metadata['phase1_lifetime']}s"
                ),
                "encryption_algorithm": [
                    p1_enc,
                ],
                "integrity_algorithm": [
                    p1_integrity,
                ],
                "dh_group": [
                    str(metadata["phase1_dh"]),
                ],
                "ike_version": (f"IKEv{metadata['ike_version']}"),
                "aggressive_mode": False,
                "lifetime_seconds": (metadata["phase1_lifetime"]),
                "authentication_method": "PSK",
            },
        )

        phase2, phase2_created = self._get_or_create_named(
            "/api/vpn/vpn-phase-2-policies/",
            phase2_name,
            {
                "name": phase2_name,
                "description": (
                    f"{plan.name} AUTO | "
                    f"{metadata['phase2_proposal']} | "
                    f"PFS/DH"
                    f"{metadata['phase2_pfs']} | "
                    f"{metadata['phase2_lifetime']}s"
                ),
                "encryption_algorithm": [
                    p2_enc,
                ],
                "integrity_algorithm": [
                    p2_integrity,
                ],
                "pfs_group": [
                    str(metadata["phase2_pfs"]),
                ],
                "lifetime": (metadata["phase2_lifetime"]),
            },
        )

        psk_vpn1 = f"********-{plan.name}-VPN1-PSK-********"

        psk_vpn2 = f"********-{plan.name}-VPN2-PSK-********"

        profile, profile_created = self._get_or_create_named(
            "/api/vpn/vpn-profiles/",
            profile_name,
            {
                "name": profile_name,
                "description": (f"AUTO S2S | PALO-ALTO-DC <-> FORTIGATE-{plan.name}"),
                "keepalive_enabled": True,
                "nat_traversal": False,
                "extra_options": {
                    "source": ("auto-onboarding"),
                    "branch": plan.name,
                    "endpoint_a": ("PALO-ALTO-DC"),
                    "endpoint_z": (f"FORTIGATE-{plan.name}"),
                    "phase1_policy_name": (phase1_name),
                    "phase1_policy_id": (phase1["id"]),
                    "phase2_policy_name": (phase2_name),
                    "phase2_policy_id": (phase2["id"]),
                    "ike_version": (metadata["ike_version"]),
                    "phase1_proposal": (metadata["phase1_proposal"]),
                    "phase1_dh": (metadata["phase1_dh"]),
                    "phase1_lifetime": (metadata["phase1_lifetime"]),
                    "phase2_proposal": (metadata["phase2_proposal"]),
                    "phase2_pfs": (metadata["phase2_pfs"]),
                    "phase2_lifetime": (metadata["phase2_lifetime"]),
                    "authentication": "PSK",
                    "vpn1_fortigate_name": ("VPN1-PA-DC"),
                    "vpn2_fortigate_name": ("VPN2-PA-DC"),
                    "psk_vpn1_placeholder": (psk_vpn1),
                    "psk_vpn2_placeholder": (psk_vpn2),
                    "real_psk_stored": False,
                    "assignment_api": ("UNAVAILABLE_HTTP_500"),
                },
            },
        )

        objects.setdefault(
            "phase1_policies",
            [],
        )

        objects.setdefault(
            "phase2_policies",
            [],
        )

        objects.setdefault(
            "vpn_profiles",
            [],
        )

        if phase1_created:
            objects["phase1_policies"].append(phase1)

        if phase2_created:
            objects["phase2_policies"].append(phase2)

        if profile_created:
            objects["vpn_profiles"].append(profile)

        # ----------------------------------------------------
        # Atualiza as duas VPNs
        # ----------------------------------------------------

        for number, vpn in enumerate(
            objects.get("vpns", []),
            start=1,
        ):
            pa_ip, fg_ip = self._overlay_hosts(
                (plan.vpn1_prefix if number == 1 else plan.vpn2_prefix)
            )

            psk_placeholder = psk_vpn1 if number == 1 else psk_vpn2

            patched = self._patch(
                "/api/vpn/vpns/",
                vpn["id"],
                {
                    "vpn_profile": (profile["id"]),
                    "description": (
                        f"VPN{number} AUTO | "
                        f"A=PALO-ALTO-DC "
                        f"{pa_ip} | "
                        f"Z=FORTIGATE-"
                        f"{plan.name} "
                        f"{fg_ip} | "
                        f"FG-TUNNEL="
                        f"VPN{number}-PA-DC | "
                        f"PSK="
                        f"{psk_placeholder}"
                    ),
                },
            )

            vpn.update(patched)

        # ----------------------------------------------------
        # Endpoints:
        # ordem criada pelo reserve:
        # VPN1 PA, VPN1 FG, VPN2 PA, VPN2 FG.
        # ----------------------------------------------------

        for endpoint in objects.get(
            "vpn_endpoints",
            [],
        ):
            patched = self._patch(
                ("/api/vpn/vpn-tunnel-endpoints/"),
                endpoint["id"],
                {
                    "vpn_profile": (profile["id"]),
                },
            )

            endpoint.update(patched)

        # ----------------------------------------------------
        # Tunnels
        # ----------------------------------------------------

        for number, tunnel in enumerate(
            objects.get(
                "vpn_tunnels",
                [],
            ),
            start=1,
        ):
            patched = self._patch(
                "/api/vpn/vpn-tunnels/",
                tunnel["id"],
                {
                    "vpn_profile": (profile["id"]),
                    "encapsulation": ("IPsec-Tunnel"),
                    "description": (
                        "A=PALO-ALTO-DC | "
                        f"Z=FORTIGATE-"
                        f"{plan.name} | "
                        f"FG=VPN{number}-PA-DC"
                    ),
                },
            )

            tunnel.update(patched)

        reservation["vpn_inventory"] = {
            "profile": profile,
            "phase1": phase1,
            "phase2": phase2,
            "psk_placeholders": {
                "vpn1": psk_vpn1,
                "vpn2": psk_vpn2,
            },
            "metadata": metadata,
        }

        return reservation

    def _delete_prefix_object(
        self,
        obj,
    ):
        self._delete(
            "/api/ipam/prefixes/",
            obj["id"],
        )

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
        Reserva o Candidate e registra no
        Nautobot o inventario dos overlays.

        A reserva inclui:
          - quatro prefixes
          - quatro IPs de tunnel
          - duas VPNs
          - quatro endpoints
          - dois VPN tunnels
        """

        plan = self.plan(branch_id=branch_id)

        created = {
            "prefixes": [],
            "ip_addresses": [],
            "vpns": [],
            "vpn_endpoints": [],
            "vpn_tunnels": [],
        }

        try:
            for (
                prefix,
                description,
            ) in self.resources_for_plan(plan):
                created["prefixes"].append(
                    self._create_prefix(
                        prefix,
                        description,
                    )
                )

            for tunnel_number, prefix in (
                (1, plan.vpn1_prefix),
                (2, plan.vpn2_prefix),
            ):
                inventory = self._create_overlay_inventory(
                    plan,
                    tunnel_number,
                    prefix,
                )

                for key in (
                    "ip_addresses",
                    "vpns",
                    "vpn_endpoints",
                    "vpn_tunnels",
                ):
                    created[key].extend(inventory[key])

        except Exception:
            try:
                self.release(created)
            except Exception:
                pass

            raise

        # Compatibilidade com o deployment
        # existente, que usa "objects".
        created["objects"] = list(created["prefixes"])

        return {
            "plan": plan,
            "objects": created,
            "created": True,
        }

    def release(
        self,
        objects,
    ):
        """
        Remove somente recursos criados por
        esta reserva.

        Ordem inversa das dependencias:
        tunnel -> endpoint -> VPN -> IP -> prefix.
        """

        if isinstance(objects, list):
            # Compatibilidade com testes/API
            # anteriores que fornecem somente
            # prefixes.
            errors = []

            for obj in reversed(objects):
                try:
                    self._delete_prefix_object(obj)
                except Exception as exc:
                    errors.append(str(exc))

            if errors:
                raise RuntimeError(
                    "Falha ao liberar recursos no Nautobot: " + "; ".join(errors)
                )

            return

        errors = []

        cleanup = (
            (
                "vpn_tunnels",
                "/api/vpn/vpn-tunnels/",
            ),
            (
                "vpn_endpoints",
                "/api/vpn/vpn-tunnel-endpoints/",
            ),
            (
                "vpns",
                "/api/vpn/vpns/",
            ),
            (
                "vpn_profiles",
                "/api/vpn/vpn-profiles/",
            ),
            (
                "phase2_policies",
                "/api/vpn/vpn-phase-2-policies/",
            ),
            (
                "phase1_policies",
                "/api/vpn/vpn-phase-1-policies/",
            ),
            (
                "ip_addresses",
                "/api/ipam/ip-addresses/",
            ),
            (
                "prefixes",
                "/api/ipam/prefixes/",
            ),
        )

        for key, path in cleanup:
            for obj in reversed(objects.get(key, [])):
                try:
                    self._delete(
                        path,
                        obj["id"],
                    )
                except Exception as exc:
                    errors.append(f"{key}:{obj.get('id')}: {exc}")

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
        """

        reservation = self.reserve(branch_id=branch_id)

        return reservation["plan"]
