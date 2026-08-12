from src.devices.base import DeviceDriver


class FortiGateDriver(DeviceDriver):
    """FortiGate device driver."""

    def apply_configuration(self, configuration: str) -> None:
        raise NotImplementedError

    def validate_configuration(self) -> bool:
        raise NotImplementedError
