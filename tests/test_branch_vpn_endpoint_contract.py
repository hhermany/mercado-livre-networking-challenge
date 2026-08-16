from ipaddress import ip_network

from src.branch.addressing import build_branch_plan


def _assert_endpoint_contract(prefix):
    network = ip_network(prefix)
    hosts = list(network.hosts())

    assert len(hosts) == 2

    # Contrato obrigatório:
    # primeiro usable = Palo Alto
    # segundo usable = FortiGate Branch
    palo_alto = hosts[0]
    fortigate = hosts[1]

    assert palo_alto == network.network_address + 1

    assert fortigate == network.network_address + 2


def test_branch_2_starts_automatic_vpn_pool():
    plan = build_branch_plan(2)

    assert plan.vpn1_prefix == "169.255.0.0/30"

    assert plan.vpn2_prefix == "169.255.0.4/30"

    _assert_endpoint_contract(plan.vpn1_prefix)

    _assert_endpoint_contract(plan.vpn2_prefix)


def test_branch_3_continues_without_waste():
    plan = build_branch_plan(3)

    assert plan.vpn1_prefix == "169.255.0.8/30"

    assert plan.vpn2_prefix == "169.255.0.12/30"

    _assert_endpoint_contract(plan.vpn1_prefix)

    _assert_endpoint_contract(plan.vpn2_prefix)


def test_vpn_pool_crosses_octet_without_waste():
    branch_33 = build_branch_plan(33)
    branch_34 = build_branch_plan(34)

    assert branch_33.vpn1_prefix == "169.255.0.248/30"

    assert branch_33.vpn2_prefix == "169.255.0.252/30"

    assert branch_34.vpn1_prefix == "169.255.1.0/30"

    assert branch_34.vpn2_prefix == "169.255.1.4/30"
