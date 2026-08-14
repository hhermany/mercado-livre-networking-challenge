from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4


@dataclass
class ManagedDevice:
    id: str
    host: str
    username: str
    password: str = field(
        repr=False,
    )
    secret: str = field(
        default="",
        repr=False,
    )
    hostname: str | None = None
    status: str = "new"
    error: str | None = None

    def credentials(self):
        return {
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "secret": self.secret,
        }

    def public(self):
        return {
            "id": self.id,
            "host": self.host,
            "username": self.username,
            "hostname": self.hostname,
            "status": self.status,
            "error": self.error,
        }


class DeviceManager:
    """
    Registro em memória dos equipamentos gerenciados.

    Senhas nunca são retornadas por list()/public().
    """

    def __init__(
        self,
        max_workers=4,
    ):
        self._devices = {}
        self._lock = RLock()
        self.max_workers = max_workers

    def add(
        self,
        *,
        host,
        username,
        password,
        secret="",
    ):
        host = (
            host
            or ""
        ).strip()

        username = (
            username
            or ""
        ).strip()

        if not host:
            raise ValueError(
                "Informe o IP ou hostname do equipamento."
            )

        if not username:
            raise ValueError(
                "Informe o usuário SSH."
            )

        if not password:
            raise ValueError(
                "Informe a senha SSH."
            )

        with self._lock:
            for device in self._devices.values():
                if device.host == host:
                    raise ValueError(
                        f"O equipamento {host} "
                        "já está cadastrado."
                    )

            device = ManagedDevice(
                id=str(uuid4()),
                host=host,
                username=username,
                password=password,
                secret=secret or "",
            )

            self._devices[
                device.id
            ] = device

        return device

    def find_by_host(
        self,
        host,
    ):
        host = (
            host
            or ""
        ).strip()

        with self._lock:
            for device in self._devices.values():
                if device.host == host:
                    return device

        return None

    def upsert(
        self,
        *,
        host,
        username,
        password,
        secret="",
    ):
        host = (
            host
            or ""
        ).strip()

        username = (
            username
            or ""
        ).strip()

        if not host:
            raise ValueError(
                "Informe o IP ou hostname do equipamento."
            )

        if not username:
            raise ValueError(
                "Informe o usuário SSH."
            )

        if not password:
            raise ValueError(
                "Informe a senha SSH."
            )

        with self._lock:
            for device in self._devices.values():
                if device.host == host:
                    device.username = username
                    device.password = password
                    device.secret = secret or ""
                    device.error = None

                    return device

            device = ManagedDevice(
                id=str(uuid4()),
                host=host,
                username=username,
                password=password,
                secret=secret or "",
            )

            self._devices[
                device.id
            ] = device

        return device

    def get(
        self,
        device_id,
    ):
        with self._lock:
            device = self._devices.get(
                device_id
            )

        if device is None:
            raise KeyError(
                "Equipamento não encontrado."
            )

        return device

    def remove(
        self,
        device_id,
    ):
        with self._lock:
            device = self._devices.pop(
                device_id,
                None,
            )

        if device is None:
            raise KeyError(
                "Equipamento não encontrado."
            )

        return device

    def list(
        self,
    ):
        with self._lock:
            devices = list(
                self._devices.values()
            )

        return [
            device.public()
            for device in devices
        ]

    def objects(
        self,
    ):
        with self._lock:
            return list(
                self._devices.values()
            )

    def clear(
        self,
    ):
        with self._lock:
            self._devices.clear()

    def discover_many(
        self,
        discover,
        device_ids=None,
    ):
        """
        Executa descoberta paralela por equipamento.

        Cada equipamento recebe no máximo um worker.
        A falha de um device não interrompe os demais.
        """

        if device_ids:
            devices = [
                self.get(
                    device_id
                )
                for device_id
                in device_ids
            ]
        else:
            devices = self.objects()

        if not devices:
            return []

        workers = min(
            self.max_workers,
            len(devices),
        )

        results = []

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:
            futures = {
                executor.submit(
                    discover,
                    device,
                ): device
                for device in devices
            }

            for future in as_completed(
                futures
            ):
                device = futures[
                    future
                ]

                try:
                    result = future.result()

                    device.hostname = (
                        result.get(
                            "hostname"
                        )
                    )

                    device.status = "connected"
                    device.error = None

                    results.append(
                        {
                            "device": (
                                device.public()
                            ),
                            "success": True,
                            **result,
                        }
                    )

                except Exception as exc:
                    device.status = "error"
                    device.error = str(exc)

                    results.append(
                        {
                            "device": (
                                device.public()
                            ),
                            "success": False,
                            "error": str(exc),
                            "interfaces": [],
                        }
                    )

        return sorted(
            results,
            key=lambda item: (
                item["device"]["host"]
            ),
        )
