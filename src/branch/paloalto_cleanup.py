from src.branch.paloalto_contract import build_paloalto_branch_plan


def generate_paloalto_branch_cleanup(branch_id: int) -> str:
    """
    Gera os comandos PAN-OS necessários para remover somente
    os objetos e referências pertencentes a uma determinada branch.

    Objetos compartilhados NÃO são removidos:
    - zone FILIAIS
    - virtual-router default
    - peer-group IBGP-SDWAN
    - IKE-FGT-PA
    - IPSEC-FGT-PA
    - TUNNEL-MGMT
    """

    if branch_id == 1:
        raise ValueError("BRANCH-1 é a golden e não pode ser destruída.")

    pa = build_paloalto_branch_plan(branch_id)

    bgp_base = (
        "delete network virtual-router default "
        "protocol bgp peer-group IBGP-SDWAN peer"
    )

    commands = [
        # BGP peers da branch
        f"{bgp_base} {pa.bgp_peer1_name}",
        f"{bgp_base} {pa.bgp_peer2_name}",

        # Referências das interfaces no virtual-router
        (
            "delete network virtual-router default "
            f"interface {pa.tunnel1_name}"
        ),
        (
            "delete network virtual-router default "
            f"interface {pa.tunnel2_name}"
        ),

        # Referências das interfaces na zona compartilhada
        f"delete zone FILIAIS network layer3 {pa.tunnel1_name}",
        f"delete zone FILIAIS network layer3 {pa.tunnel2_name}",

        # Túneis IPsec específicos da branch
        f"delete network tunnel ipsec {pa.ipsec1_name}",
        f"delete network tunnel ipsec {pa.ipsec2_name}",

        # IKE gateways específicos da branch
        f"delete network ike gateway {pa.ipsec1_name}",
        f"delete network ike gateway {pa.ipsec2_name}",

        # Tunnel interfaces específicas da branch
        (
            "delete network interface tunnel units "
            f"{pa.tunnel1_name}"
        ),
        (
            "delete network interface tunnel units "
            f"{pa.tunnel2_name}"
        ),
    ]

    return "\n".join(commands)
