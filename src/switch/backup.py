from __future__ import annotations

import posixpath
from dataclasses import dataclass
from ftplib import FTP
from io import BytesIO
from pathlib import Path

SUPPORTED_BACKUP_PROTOCOLS = {
    "local",
    "ftp",
    "sftp",
    "tftp",
}


@dataclass(frozen=True)
class BackupStorageResult:
    protocol: str
    destination: str
    filename: str
    size: int


def validate_backup_protocol(protocol):
    normalized = (protocol or "local").strip().lower()

    if normalized not in SUPPORTED_BACKUP_PROTOCOLS:
        raise ValueError("Destino de backup inválido.")

    return normalized


def store_local_backup(
    content,
    filename,
    directory="backups",
):
    destination_directory = Path(directory)

    destination_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = destination_directory / filename

    destination.write_bytes(content)

    return BackupStorageResult(
        protocol="local",
        destination=str(destination),
        filename=filename,
        size=len(content),
    )


def _validate_ftp_parameters(
    host,
    port,
    username,
    password,
):
    if not host or not host.strip():
        raise ValueError("Informe o servidor FTP.")

    if not username or not username.strip():
        raise ValueError("Informe o usuário FTP.")

    if not password:
        raise ValueError("Informe a senha FTP.")

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("Porta FTP inválida.") from exc

    if not 1 <= port <= 65535:
        raise ValueError("Porta FTP inválida.")

    return port


def _normalize_ftp_directory(
    remote_directory,
):
    value = (remote_directory or "/").strip()

    if not value:
        return "/"

    # FTP usa caminhos POSIX mesmo quando o servidor
    # está hospedado em Windows/IIS.
    normalized = posixpath.normpath("/" + value.lstrip("/"))

    if normalized.startswith("/../"):
        raise ValueError("Diretório FTP inválido.")

    return normalized


def store_ftp_backup(
    content,
    filename,
    host,
    port=21,
    username=None,
    password=None,
    remote_directory="/",
    timeout=15,
):
    port = _validate_ftp_parameters(
        host=host,
        port=port,
        username=username,
        password=password,
    )

    remote_directory = _normalize_ftp_directory(remote_directory)

    ftp = FTP()

    try:
        ftp.connect(
            host.strip(),
            port,
            timeout=timeout,
        )

        ftp.login(
            username.strip(),
            password,
        )

        ftp.set_pasv(True)

        if remote_directory != "/":
            ftp.cwd(remote_directory)

        response = ftp.storbinary(
            f"STOR {filename}",
            BytesIO(content),
        )

        if not response.startswith("226"):
            raise RuntimeError(
                "Servidor FTP não confirmou a conclusão da transferência."
            )

        remote_path = posixpath.join(
            remote_directory,
            filename,
        )

        return BackupStorageResult(
            protocol="ftp",
            destination=(f"ftp://{host.strip()}:{port}{remote_path}"),
            filename=filename,
            size=len(content),
        )

    finally:
        try:
            ftp.quit()
        except Exception:
            try:
                ftp.close()
            except Exception:
                pass


def _validate_sftp_parameters(
    host,
    port,
    username,
    password,
):
    if not host or not host.strip():
        raise ValueError("Informe o servidor SFTP.")

    if not username or not username.strip():
        raise ValueError("Informe o usuário SFTP.")

    if not password:
        raise ValueError("Informe a senha SFTP.")

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("Porta SFTP inválida.") from exc

    if not 1 <= port <= 65535:
        raise ValueError("Porta SFTP inválida.")

    return port


def _normalize_sftp_directory(
    remote_directory,
):
    value = (remote_directory or "/").strip()

    if not value:
        return "/"

    normalized = posixpath.normpath("/" + value.lstrip("/"))

    if normalized.startswith("/../"):
        raise ValueError("Diretório SFTP inválido.")

    return normalized


def store_sftp_backup(
    content,
    filename,
    host,
    port=22,
    username=None,
    password=None,
    remote_directory="/",
    timeout=15,
):
    import paramiko

    port = _validate_sftp_parameters(
        host=host,
        port=port,
        username=username,
        password=password,
    )

    remote_directory = _normalize_sftp_directory(remote_directory)

    client = paramiko.SSHClient()

    client.load_system_host_keys()

    # Para o laboratório, permite conexão com hosts ainda
    # não registrados no known_hosts.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    sftp = None

    try:
        client.connect(
            hostname=host.strip(),
            port=port,
            username=username.strip(),
            password=password,
            timeout=timeout,
            auth_timeout=timeout,
            banner_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )

        sftp = client.open_sftp()

        if remote_directory != "/":
            sftp.chdir(remote_directory)

        remote_path = posixpath.join(
            remote_directory,
            filename,
        )

        with sftp.file(
            filename,
            mode="wb",
        ) as remote_file:
            remote_file.write(content)

            remote_file.flush()

        # Confirma que o arquivo existe e que o tamanho
        # corresponde ao conteúdo enviado.
        attributes = sftp.stat(filename)

        if attributes.st_size != len(content):
            raise RuntimeError(
                "O servidor SFTP recebeu um arquivo com tamanho diferente do esperado."
            )

        return BackupStorageResult(
            protocol="sftp",
            destination=(f"sftp://{host.strip()}:{port}{remote_path}"),
            filename=filename,
            size=len(content),
        )

    finally:
        if sftp is not None:
            try:
                sftp.close()
            except Exception:
                pass

        try:
            client.close()
        except Exception:
            pass


def _validate_tftp_parameters(
    host,
    port,
):
    if not host or not host.strip():
        raise ValueError("Informe o servidor TFTP.")

    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("Porta TFTP inválida.") from exc

    if not 1 <= port <= 65535:
        raise ValueError("Porta TFTP inválida.")

    return port


def _normalize_tftp_directory(
    remote_directory,
):
    value = (remote_directory or "/").strip()

    if not value:
        return "/"

    normalized = posixpath.normpath("/" + value.lstrip("/"))

    if normalized.startswith("/../"):
        raise ValueError("Diretório TFTP inválido.")

    return normalized


def store_tftp_backup(
    content,
    filename,
    host,
    port=69,
    remote_directory="/",
    timeout=5,
):
    import tempfile

    import tftpy

    port = _validate_tftp_parameters(
        host=host,
        port=port,
    )

    remote_directory = _normalize_tftp_directory(remote_directory)

    remote_path = posixpath.join(
        remote_directory,
        filename,
    ).lstrip("/")

    # TFTPy trabalha naturalmente com filename local.
    # Criamos arquivo temporário apenas durante a transferência.
    with tempfile.NamedTemporaryFile(
        mode="wb",
        delete=True,
    ) as temporary:
        temporary.write(content)
        temporary.flush()

        client = tftpy.TftpClient(
            host.strip(),
            port,
        )

        client.upload(
            remote_path,
            temporary.name,
            timeout=timeout,
        )

    return BackupStorageResult(
        protocol="tftp",
        destination=(f"tftp://{host.strip()}:{port}/{remote_path}"),
        filename=filename,
        size=len(content),
    )


def store_backup(
    *,
    protocol,
    content,
    filename,
    local_directory="backups",
    host=None,
    port=None,
    username=None,
    password=None,
    remote_directory="/",
):
    protocol = validate_backup_protocol(protocol)

    if protocol == "local":
        return store_local_backup(
            content=content,
            filename=filename,
            directory=local_directory,
        )

    if protocol == "ftp":
        return store_ftp_backup(
            content=content,
            filename=filename,
            host=host,
            port=(port if port is not None else 21),
            username=username,
            password=password,
            remote_directory=remote_directory,
        )

    if protocol == "sftp":
        return store_sftp_backup(
            content=content,
            filename=filename,
            host=host,
            port=(port if port is not None else 22),
            username=username,
            password=password,
            remote_directory=remote_directory,
        )

    if protocol == "tftp":
        return store_tftp_backup(
            content=content,
            filename=filename,
            host=host,
            port=(port if port is not None else 69),
            remote_directory=remote_directory,
        )

    raise ValueError("Destino de backup não suportado.")
