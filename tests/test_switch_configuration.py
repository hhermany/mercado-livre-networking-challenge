from datetime import datetime

import pytest

from src.switch.configuration import (
    build_backup_filename,
    compare_cisco_configs,
    extract_hostname,
    normalize_config_text,
    validate_config_filename,
)


def test_normalize_removes_ios_volatile_headers():
    config = """\
Building configuration...

Current configuration : 3033 bytes
!
! Last configuration change at 22:34:42 UTC Thu Aug 13 2026 by admin
!
version 15.2
hostname SW1
"""

    result = normalize_config_text(
        config
    )

    assert "Building configuration" not in result
    assert "Current configuration" not in result
    assert "Last configuration change" not in result

    assert "version 15.2" in result
    assert "hostname SW1" in result


def test_normalize_removes_startup_memory_header():
    config = """\
Using 1541 out of 262144 bytes, uncompressed size = 2819 bytes
!
version 15.2
"""

    result = normalize_config_text(
        config
    )

    assert "Using 1541" not in result
    assert "version 15.2" in result


def test_extract_hostname():
    assert extract_hostname(
        "version 15.2\nhostname SW-TESTE1\n"
    ) == "SW-TESTE1"


def test_extract_hostname_fallback():
    assert extract_hostname(
        "version 15.2\n"
    ) == "switch"


@pytest.mark.parametrize(
    "filename",
    [
        "switch.cfg",
        "switch.conf",
        "switch.txt",
    ],
)
def test_validate_config_filename(filename):
    assert validate_config_filename(
        filename
    )


def test_validate_config_filename_rejects_binary():
    with pytest.raises(ValueError):
        validate_config_filename(
            "switch.exe"
        )


def test_build_backup_filename():
    result = build_backup_filename(
        hostname="SW-TESTE1",
        config_type="running",
        timestamp=datetime(
            2026,
            8,
            14,
            1,
            2,
            3,
        ),
    )

    assert result == (
        "SW-TESTE1_running_20260814_010203.cfg"
    )


def test_compare_detects_running_only_interface():
    startup = """\
version 15.2
!
interface GigabitEthernet0/0
 no switchport
!
"""

    running = """\
version 15.2
!
interface Port-channel1
 switchport trunk allowed vlan 10,20
 switchport mode trunk
!
interface GigabitEthernet0/0
 no switchport
!
"""

    result = compare_cisco_configs(
        startup,
        running,
    )

    section = next(
        item
        for item in result.changed_sections
        if item.name == "interface Port-channel1"
    )

    assert section.status == "running_only"

    assert (
        " switchport mode trunk"
        in section.added_lines
    )


def test_compare_detects_modified_interface():
    startup = """\
interface GigabitEthernet1/2
 switchport access vlan 101
 switchport mode access
!
"""

    running = """\
interface GigabitEthernet1/2
 switchport trunk allowed vlan 10,20
 switchport mode trunk
 channel-group 1 mode active
!
"""

    result = compare_cisco_configs(
        startup,
        running,
    )

    assert result.changed_count == 1

    section = result.changed_sections[0]

    assert section.status == "modified"

    assert (
        " switchport access vlan 101"
        in section.removed_lines
    )

    assert (
        " switchport mode trunk"
        in section.added_lines
    )


def test_compare_identical_configs():
    config = """\
version 15.2
!
hostname SW1
!
"""

    result = compare_cisco_configs(
        config,
        config,
    )

    assert result.identical is True
    assert result.changed_count == 0


def test_global_commands_are_compared_as_one_section():
    startup = """\
version 15.2
!
hostname SW-TESTE1
!
ip ssh version 2
ip ssh server algorithm encryption aes128-ctr aes192-ctr aes256-ctr
ip ssh client algorithm encryption aes128-ctr aes192-ctr aes256-ctr
!
"""

    running = """\
version 15.2
!
hostname SW-TESTE1
!
ip route 0.0.0.0 0.0.0.0 172.28.255.254
ip ssh version 2
ip ssh server algorithm encryption aes128-ctr aes192-ctr aes256-ctr
ip ssh client algorithm encryption aes128-ctr aes192-ctr aes256-ctr
!
"""

    result = compare_cisco_configs(
        startup,
        running,
    )

    global_section = next(
        section
        for section in result.changed_sections
        if section.name == "Configuração global"
    )

    assert global_section.status == "modified"

    assert global_section.removed_lines == ()

    assert global_section.added_lines == (
        "ip route 0.0.0.0 0.0.0.0 "
        "172.28.255.254",
    )

    assert (
        "ip ssh version 2"
        not in global_section.added_lines
    )

    assert (
        "ip ssh version 2"
        not in global_section.removed_lines
    )


def test_configuration_flows_do_not_implicitly_save():
    from pathlib import Path

    source = Path(
        "src/switch/cisco.py"
    ).read_text()

    assert "conn.save_config()" not in source

    assert (
        "copy running-config startup-config"
        in source
    )


def test_aligns_same_configuration_topics_side_by_side():
    startup = """\
interface GigabitEthernet0/2
 switchport access vlan 101
 spanning-tree portfast edge
!
"""

    running = """\
interface GigabitEthernet0/2
 switchport access vlan 50
 spanning-tree portfast disable
!
"""

    result = compare_cisco_configs(
        startup,
        running,
    )

    section = result.changed_sections[0]

    assert len(section.rows) == 2

    assert (
        section.rows[0].startup_line
        == " switchport access vlan 101"
    )

    assert (
        section.rows[0].running_line
        == " switchport access vlan 50"
    )

    assert (
        section.rows[1].startup_line
        == " spanning-tree portfast edge"
    )

    assert (
        section.rows[1].running_line
        == " spanning-tree portfast disable"
    )
