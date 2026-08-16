from src.branch.paloalto_contract import (
    build_paloalto_branch_plan,
)


def test_branch_1_uses_tunnel_1_and_2():
    plan = build_paloalto_branch_plan(1)

    assert plan.tunnel1_name == "tunnel.1"
    assert plan.tunnel2_name == "tunnel.2"


def test_branch_2_uses_tunnel_3_and_4():
    plan = build_paloalto_branch_plan(2)

    assert plan.tunnel1_name == "tunnel.3"
    assert plan.tunnel2_name == "tunnel.4"


def test_branch_3_uses_tunnel_5_and_6():
    plan = build_paloalto_branch_plan(3)

    assert plan.tunnel1_name == "tunnel.5"
    assert plan.tunnel2_name == "tunnel.6"
