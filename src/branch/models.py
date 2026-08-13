from dataclasses import dataclass


@dataclass(frozen=True)
class BranchWANInput:
    wan1_ip: str
    wan1_gateway: str
    wan2_ip: str
    wan2_gateway: str


@dataclass(frozen=True)
class BranchActivation:
    branch_id: int
    wan: BranchWANInput
    psk: str
