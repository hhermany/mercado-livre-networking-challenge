from dataclasses import dataclass, field


@dataclass(frozen=True)
class BranchVariables:
    hostname: str
    management_ip: str
    management_mask: str
    default_gateway: str
    uplink_interface: str


@dataclass(frozen=True)
class InterfaceClassification:
    uplink: str
    provision_port: str
    provision_ip: str | None = None
    user_ports: list[str] = field(default_factory=list)
    preserved_ports: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProvisionPlan:
    device_id: str
    profile_name: str
    variables: BranchVariables
    interfaces: InterfaceClassification
