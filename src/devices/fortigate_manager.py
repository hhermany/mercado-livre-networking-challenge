from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken


@dataclass
class ManagedFortiGate:
    id: str
    host: str
    username: str
    password: str = field(repr=False)
    hostname: str | None = None
    status: str = "new"
    error: str | None = None

    def credentials(self):
        return {
            "host": self.host,
            "username": self.username,
            "password": self.password,
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


class FortiGateManager:
    def __init__(self):
        self._devices = {}
        self._lock = RLock()

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

    def _load_or_create_key(self):
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

    def _connect(self):
        if self._database_path is None:
            raise RuntimeError("Persistência não habilitada.")

        return sqlite3.connect(self._database_path)

    def _initialize_database(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS fortigates (
                    id TEXT PRIMARY KEY,
                    host TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    password BLOB NOT NULL,
                    hostname TEXT,
                    status TEXT NOT NULL,
                    error TEXT
                )
                """
            )

    def _encrypt(self, value):
        if self._cipher is None:
            raise RuntimeError("Cipher não inicializado.")

        return self._cipher.encrypt((value or "").encode("utf-8"))

    def _decrypt(self, value):
        if self._cipher is None:
            raise RuntimeError("Cipher não inicializado.")

        try:
            return self._cipher.decrypt(value).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError(
                "Não foi possível descriptografar "
                "as credenciais persistidas do FortiGate."
            ) from exc

    def _save_device(self, device):
        if not self.persistent:
            return

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO fortigates (
                    id,
                    host,
                    username,
                    password,
                    hostname,
                    status,
                    error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id)
                DO UPDATE SET
                    host = excluded.host,
                    username = excluded.username,
                    password = excluded.password,
                    hostname = excluded.hostname,
                    status = excluded.status,
                    error = excluded.error
                """,
                (
                    device.id,
                    device.host,
                    device.username,
                    self._encrypt(device.password),
                    device.hostname,
                    device.status,
                    device.error,
                ),
            )

    def _delete_device(self, device_id):
        if not self.persistent:
            return

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM fortigates
                WHERE id = ?
                """,
                (device_id,),
            )

    def _load_database(self):
        loaded = {}

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    host,
                    username,
                    password,
                    hostname,
                    status,
                    error
                FROM fortigates
                ORDER BY host
                """
            ).fetchall()

        for row in rows:
            device = ManagedFortiGate(
                id=row[0],
                host=row[1],
                username=row[2],
                password=self._decrypt(row[3]),
                hostname=row[4],
                status=row[5],
                error=row[6],
            )

            loaded[device.id] = device

        with self._lock:
            self._devices = loaded

    def upsert(
        self,
        *,
        host,
        username,
        password,
    ):
        host = (host or "").strip()
        username = (username or "").strip()

        if not host:
            raise ValueError("Informe o IP ou hostname do FortiGate.")

        if not username:
            raise ValueError("Informe o usuário SSH.")

        if not password:
            raise ValueError("Informe a senha SSH.")

        with self._lock:
            for device in self._devices.values():
                if device.host == host:
                    device.username = username
                    device.password = password
                    device.error = None

                    self._save_device(device)
                    return device

            device = ManagedFortiGate(
                id=str(uuid4()),
                host=host,
                username=username,
                password=password,
            )

            self._devices[device.id] = device
            self._save_device(device)

        return device

    def save(self, device):
        with self._lock:
            if device.id not in self._devices:
                raise KeyError("FortiGate não encontrado.")

            self._save_device(device)

        return device

    def get(self, device_id):
        with self._lock:
            device = self._devices.get(device_id)

        if device is None:
            raise KeyError("FortiGate não encontrado.")

        return device

    def remove(self, device_id):
        with self._lock:
            device = self._devices.pop(
                device_id,
                None,
            )

            if device is None:
                raise KeyError("FortiGate não encontrado.")

            self._delete_device(device_id)

        return device

    def list(self):
        with self._lock:
            devices = list(self._devices.values())

        return [device.public() for device in devices]

    def clear(self):
        with self._lock:
            device_ids = list(self._devices)

            self._devices.clear()

            for device_id in device_ids:
                self._delete_device(device_id)
