from __future__ import annotations

import os
import sqlite3
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from uuid import uuid4

from cryptography.fernet import (
    Fernet,
    InvalidToken,
)


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
    Registro dos equipamentos gerenciados.

    Por padrão funciona somente em memória.

    A aplicação operacional habilita persistência
    explicitamente ao iniciar o Flask.
    """

    def __init__(
        self,
        max_workers=4,
    ):
        self._devices = {}
        self._lock = RLock()
        self.max_workers = max_workers

        self._database_path = None
        self._key_path = None
        self._cipher = None

    @property
    def persistent(self):
        return self._database_path is not None

    def enable_persistence(
        self,
        *,
        database_path,
        key_path,
    ):
        database_path = Path(database_path)

        key_path = Path(key_path)

        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        key_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._database_path = database_path

        self._key_path = key_path

        self._cipher = Fernet(self._load_or_create_key())

        self._initialize_database()
        self._load_database()

    def _load_or_create_key(
        self,
    ):
        if self._key_path.exists():
            return self._key_path.read_bytes()

        key = Fernet.generate_key()

        self._key_path.write_bytes(key)

        try:
            os.chmod(
                self._key_path,
                0o600,
            )
        except OSError:
            pass

        return key

    def _connect(
        self,
    ):
        if self._database_path is None:
            raise RuntimeError("Persistência não habilitada.")

        return sqlite3.connect(self._database_path)

    def _initialize_database(
        self,
    ):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    host TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    password BLOB NOT NULL,
                    secret BLOB NOT NULL,
                    hostname TEXT,
                    status TEXT NOT NULL,
                    error TEXT
                )
                """
            )

    def _encrypt(
        self,
        value,
    ):
        if self._cipher is None:
            raise RuntimeError("Cipher não inicializado.")

        return self._cipher.encrypt((value or "").encode("utf-8"))

    def _decrypt(
        self,
        value,
    ):
        if self._cipher is None:
            raise RuntimeError("Cipher não inicializado.")

        try:
            return self._cipher.decrypt(value).decode("utf-8")

        except InvalidToken as exc:
            raise RuntimeError(
                "Não foi possível descriptografar as credenciais persistidas."
            ) from exc

    def _save_device(
        self,
        device,
    ):
        if not self.persistent:
            return

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO devices (
                    id,
                    host,
                    username,
                    password,
                    secret,
                    hostname,
                    status,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    host = excluded.host,
                    username = excluded.username,
                    password = excluded.password,
                    secret = excluded.secret,
                    hostname = excluded.hostname,
                    status = excluded.status,
                    error = excluded.error
                """,
                (
                    device.id,
                    device.host,
                    device.username,
                    self._encrypt(device.password),
                    self._encrypt(device.secret),
                    device.hostname,
                    device.status,
                    device.error,
                ),
            )

    def _load_database(
        self,
    ):
        loaded = {}

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    host,
                    username,
                    password,
                    secret,
                    hostname,
                    status,
                    error
                FROM devices
                ORDER BY host
                """
            ).fetchall()

        for row in rows:
            device = ManagedDevice(
                id=row[0],
                host=row[1],
                username=row[2],
                password=self._decrypt(row[3]),
                secret=self._decrypt(row[4]),
                hostname=row[5],
                status=row[6],
                error=row[7],
            )

            loaded[device.id] = device

        with self._lock:
            self._devices = loaded

    def add(
        self,
        *,
        host,
        username,
        password,
        secret="",
    ):
        host = (host or "").strip()

        username = (username or "").strip()

        if not host:
            raise ValueError("Informe o IP ou hostname do equipamento.")

        if not username:
            raise ValueError("Informe o usuário SSH.")

        if not password:
            raise ValueError("Informe a senha SSH.")

        with self._lock:
            for device in self._devices.values():
                if device.host == host:
                    raise ValueError(f"O equipamento {host} já está cadastrado.")

            device = ManagedDevice(
                id=str(uuid4()),
                host=host,
                username=username,
                password=password,
                secret=secret or "",
            )

            self._devices[device.id] = device

        self._save_device(device)

        return device

    def find_by_host(
        self,
        host,
    ):
        host = (host or "").strip()

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
        host = (host or "").strip()

        username = (username or "").strip()

        if not host:
            raise ValueError("Informe o IP ou hostname do equipamento.")

        if not username:
            raise ValueError("Informe o usuário SSH.")

        if not password:
            raise ValueError("Informe a senha SSH.")

        with self._lock:
            existing = None

            for device in self._devices.values():
                if device.host == host:
                    existing = device
                    break

            if existing is not None:
                existing.username = username
                existing.password = password
                existing.secret = secret or ""
                existing.error = None

                device = existing

            else:
                device = ManagedDevice(
                    id=str(uuid4()),
                    host=host,
                    username=username,
                    password=password,
                    secret=secret or "",
                )

                self._devices[device.id] = device

        self._save_device(device)

        return device

    def get(
        self,
        device_id,
    ):
        with self._lock:
            device = self._devices.get(device_id)

        if device is None:
            raise KeyError("Equipamento não encontrado.")

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
            raise KeyError("Equipamento não encontrado.")

        if self.persistent:
            with self._connect() as connection:
                connection.execute(
                    """
                    DELETE FROM devices
                    WHERE id = ?
                    """,
                    (device_id,),
                )

        return device

    def list(
        self,
    ):
        with self._lock:
            devices = list(self._devices.values())

        return [device.public() for device in devices]

    def objects(
        self,
    ):
        with self._lock:
            return list(self._devices.values())

    def clear(
        self,
    ):
        with self._lock:
            self._devices.clear()

        if self.persistent:
            with self._connect() as connection:
                connection.execute("DELETE FROM devices")

    def discover_many(
        self,
        discover,
        device_ids=None,
    ):
        if device_ids:
            devices = [self.get(device_id) for device_id in device_ids]
        else:
            devices = self.objects()

        if not devices:
            return []

        workers = min(
            self.max_workers,
            len(devices),
        )

        results = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    discover,
                    device,
                ): device
                for device in devices
            }

            for future in as_completed(futures):
                device = futures[future]

                try:
                    result = future.result()

                    device.hostname = result.get("hostname") or device.hostname

                    device.status = "connected"
                    device.error = None

                    self._save_device(device)

                    results.append(
                        {
                            "device": device.public(),
                            "success": True,
                            **result,
                        }
                    )

                except Exception as exc:
                    device.status = "error"
                    device.error = str(exc)

                    self._save_device(device)

                    results.append(
                        {
                            "device": device.public(),
                            "success": False,
                            "error": str(exc),
                            "interfaces": [],
                        }
                    )

        return sorted(
            results,
            key=lambda item: item["device"]["host"],
        )
