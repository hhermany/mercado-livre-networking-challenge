BRANCH_STANDARD_V1 = {
    "name": "Branch Standard v1",
    # ======================================================
    # VLANs
    # ======================================================
    "management_vlan": 255,
    "access_vlan": 10,
    "voice_vlan": 20,
    "allowed_vlans": [
        10,
        20,
        255,
    ],
    # ======================================================
    # Administração
    # ======================================================
    "admin_login_authentication": "local",
    # ======================================================
    # Wired NAC
    # ======================================================
    "dot1x_mode": "open",
    # ======================================================
    # Sistema
    # ======================================================
    "timezone": "GMT -3 0",
    "domain_name": "MercadoLivre.local",
    # Sintaxe atual do Candidate.
    #
    # O próximo incremento implementará o preflight
    # por equipamento para escolher dinamicamente:
    #
    # ip domain name
    # ou
    # ip domain-name
    #
    "domain_command": "ip domain name",
    "name_servers": [
        "192.168.1.1",
        "192.168.1.2",
    ],
    "enable_secret": ("$9$ZOHVgQhqPSPloU$MvZQXnEHnjUGcrwO4HVogGxwaxFx7eYK.EoP2oGF5u6"),
    # ======================================================
    # DHCP Snooping
    #
    # Deliberadamente abrangente.
    # VLANs criadas futuramente já ficam cobertas.
    # ======================================================
    "dhcp_snooping_vlan_range": "1-4094",
    # ======================================================
    # STP
    # ======================================================
    "spanning_tree_mode": "rapid-pvst",
    # ======================================================
    # SNMP
    # ======================================================
    "snmp_community_ro": "MercadoLibre007",
    "snmp_host": "192.168.0.167",
    # ======================================================
    # Logging
    # ======================================================
    "logging_buffered": 102400,
    "syslog_servers": [
        {
            "address": "192.168.0.178",
            "port": 20514,
        },
        {
            "address": "192.168.0.177",
            "port": 20514,
        },
        {
            "address": "192.168.0.38",
            "port": None,
        },
    ],
    # ======================================================
    # NTP
    # ======================================================
    "ntp_servers": [
        "192.168.1.1",
        "10.20.10.193",
    ],
    # ======================================================
    # RADIUS
    # ======================================================
    "radius_group": "RAD",
    "radius_servers": [
        {
            "name": "RAD1",
            "address": "192.168.0.178",
            "auth_port": 1645,
            "acct_port": 1646,
            "timeout": 10,
            "retransmit": 3,
            "radius_key": "094F471A1A0A",
            "coa_key": "13061E010803",
        },
        {
            "name": "RAD2",
            "address": "192.168.0.177",
            "auth_port": 1645,
            "acct_port": 1646,
            "timeout": 10,
            "retransmit": 3,
            "radius_key": "070C285F4D06",
            "coa_key": "0822455D0A16",
        },
    ],
}
