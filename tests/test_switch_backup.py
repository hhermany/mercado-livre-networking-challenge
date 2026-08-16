from io import BytesIO

import pytest

import src.switch.backup as backup


class FakeFTP:
    instances = []

    def __init__(self):
        self.connected = None
        self.logged_in = None
        self.passive = None
        self.directory = "/"
        self.command = None
        self.content = None
        self.closed = False

        self.__class__.instances.append(self)

    def connect(
        self,
        host,
        port,
        timeout,
    ):
        self.connected = (
            host,
            port,
            timeout,
        )

    def login(
        self,
        username,
        password,
    ):
        self.logged_in = (
            username,
            password,
        )

    def set_pasv(
        self,
        enabled,
    ):
        self.passive = enabled

    def cwd(
        self,
        directory,
    ):
        self.directory = directory

    def storbinary(
        self,
        command,
        fileobj,
    ):
        assert isinstance(
            fileobj,
            BytesIO,
        )

        self.command = command
        self.content = fileobj.read()

        return "226 Transfer complete."

    def quit(self):
        self.closed = True

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clear_fake_ftp():
    FakeFTP.instances.clear()


def test_ftp_backup_upload(
    monkeypatch,
):
    monkeypatch.setattr(
        backup,
        "FTP",
        FakeFTP,
    )

    result = backup.store_ftp_backup(
        content=b"hostname SW1\n",
        filename="SW1.cfg",
        host="192.0.2.10",
        port=21,
        username="admin",
        password="password",
        remote_directory="/configs",
    )

    ftp = FakeFTP.instances[0]

    assert ftp.connected == (
        "192.0.2.10",
        21,
        15,
    )

    assert ftp.logged_in == (
        "admin",
        "password",
    )

    assert ftp.passive is True
    assert ftp.directory == "/configs"

    assert ftp.command == ("STOR SW1.cfg")

    assert ftp.content == (b"hostname SW1\n")

    assert result.protocol == "ftp"

    assert result.destination == ("ftp://192.0.2.10:21/configs/SW1.cfg")


def test_ftp_backup_requires_credentials():
    with pytest.raises(
        ValueError,
        match="usuário FTP",
    ):
        backup.store_ftp_backup(
            content=b"test",
            filename="test.cfg",
            host="192.0.2.10",
            username="",
            password="password",
        )


def test_local_backup_storage(
    tmp_path,
):
    result = backup.store_local_backup(
        content=b"hostname SW1\n",
        filename="SW1.cfg",
        directory=tmp_path,
    )

    assert result.protocol == "local"

    assert (tmp_path / "SW1.cfg").read_bytes() == (b"hostname SW1\n")


class FakeSFTPFile:
    def __init__(self):
        self.content = b""

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False

    def write(
        self,
        content,
    ):
        self.content += content

    def flush(self):
        pass


class FakeSFTPAttributes:
    def __init__(
        self,
        size,
    ):
        self.st_size = size


class FakeSFTPClient:
    def __init__(self):
        self.directory = "/"
        self.files = {}
        self.closed = False

    def chdir(
        self,
        directory,
    ):
        self.directory = directory

    def file(
        self,
        filename,
        mode,
    ):
        assert mode == "wb"

        remote_file = FakeSFTPFile()

        self.files[filename] = remote_file

        return remote_file

    def stat(
        self,
        filename,
    ):
        return FakeSFTPAttributes(len(self.files[filename].content))

    def close(self):
        self.closed = True


class FakeSSHClient:
    instances = []

    def __init__(self):
        self.policy = None
        self.connected = None
        self.closed = False
        self.sftp = FakeSFTPClient()

        self.__class__.instances.append(self)

    def load_system_host_keys(self):
        pass

    def set_missing_host_key_policy(
        self,
        policy,
    ):
        self.policy = policy

    def connect(
        self,
        **kwargs,
    ):
        self.connected = kwargs

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


def test_sftp_backup_upload(
    monkeypatch,
):
    import paramiko

    FakeSSHClient.instances.clear()

    monkeypatch.setattr(
        paramiko,
        "SSHClient",
        FakeSSHClient,
    )

    result = backup.store_sftp_backup(
        content=b"hostname SW1\n",
        filename="SW1.cfg",
        host="192.0.2.20",
        port=22,
        username="admin",
        password="password",
        remote_directory="/configs",
    )

    client = FakeSSHClient.instances[0]

    assert client.connected["hostname"] == "192.0.2.20"

    assert client.connected["port"] == 22

    assert client.connected["username"] == "admin"

    assert client.sftp.directory == ("/configs")

    assert client.sftp.files["SW1.cfg"].content == b"hostname SW1\n"

    assert result.protocol == "sftp"

    assert result.destination == ("sftp://192.0.2.20:22/configs/SW1.cfg")


def test_sftp_requires_credentials():
    with pytest.raises(
        ValueError,
        match="usuário SFTP",
    ):
        backup.store_sftp_backup(
            content=b"test",
            filename="test.cfg",
            host="192.0.2.20",
            username="",
            password="password",
        )


def test_tftp_backup_upload(
    monkeypatch,
    tmp_path,
):
    import sys
    import types

    captured = {}

    class FakeTftpClient:
        def __init__(
            self,
            host,
            port,
        ):
            captured["host"] = host
            captured["port"] = port

        def upload(
            self,
            remote_name,
            local_name,
            timeout,
        ):
            captured["remote_name"] = remote_name

            captured["timeout"] = timeout

            captured["content"] = open(
                local_name,
                "rb",
            ).read()

    fake_module = types.SimpleNamespace(TftpClient=FakeTftpClient)

    monkeypatch.setitem(
        sys.modules,
        "tftpy",
        fake_module,
    )

    result = backup.store_tftp_backup(
        content=b"hostname SW1\n",
        filename="SW1.cfg",
        host="192.0.2.30",
        port=69,
        remote_directory="/configs",
    )

    assert captured["host"] == "192.0.2.30"

    assert captured["port"] == 69

    assert captured["remote_name"] == "configs/SW1.cfg"

    assert captured["content"] == b"hostname SW1\n"

    assert result.protocol == "tftp"

    assert result.destination == ("tftp://192.0.2.30:69/configs/SW1.cfg")


def test_tftp_requires_host():
    with pytest.raises(
        ValueError,
        match="servidor TFTP",
    ):
        backup.store_tftp_backup(
            content=b"test",
            filename="test.cfg",
            host="",
        )
