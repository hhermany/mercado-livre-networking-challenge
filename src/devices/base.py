from abc import ABC, abstractmethod


class DeviceDriver(ABC):
    """Common interface for network device configuration drivers."""

    @abstractmethod
    def apply_configuration(self, configuration: str) -> None:
        """Apply rendered configuration to the device."""

    @abstractmethod
    def validate_configuration(self) -> bool:
        """Validate whether the expected configuration is active."""
