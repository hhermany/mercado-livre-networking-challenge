from abc import ABC, abstractmethod


class IPAMProvider(ABC):
    """Define the interface required by IPAM implementations."""

    @abstractmethod
    def allocate_prefix(self, prefix_length: int, description: str) -> dict:
        """Allocate and return the next available prefix."""

    @abstractmethod
    def release_prefix(self, prefix_id: str) -> None:
        """Release a previously allocated prefix."""
