from dataclasses import dataclass


@dataclass(frozen=True)
class BranchWANInput:
    wan1_ip: str
    wan1_gateway: str
    wan2_ip: str
    wan2_gateway: str


@dataclass(frozen=True)
class IPsecPhase1Input:
    ike_version: int
    proposal: str
    dh_group: int
    psk: str


@dataclass(frozen=True)
class IPsecPhase2Input:
    proposal: str
    dh_group: int


@dataclass(frozen=True)
class BranchProvisionInput:
    hostname: str
    wan: BranchWANInput
    phase1: IPsecPhase1Input
    phase2: IPsecPhase2Input


@dataclass(frozen=True)
class BranchActivation:
    branch_id: int
    wan: BranchWANInput
    psk: str
