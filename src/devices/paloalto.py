from src.devices.base import DeviceDriver


class PaloAltoDriver(DeviceDriver):
    """Palo Alto device driver."""

    def apply_configuration(self, configuration: str) -> None:
        raise NotImplementedError

    def validate_configuration(self) -> bool:
        raise NotImplementedError
