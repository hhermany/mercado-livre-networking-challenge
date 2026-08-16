def test_cli_errors_are_warnings_until_post_validation():
    from src.devices.fortigate import (
        FortiGateDriver,
    )

    output = """\
config system interface
Command fail. Return code -61
end
"""

    warnings = FortiGateDriver._assert_cli_success(output)

    assert warnings
    assert any("command fail" in value.lower() for value in warnings)


def test_clean_cli_has_no_warnings():
    from src.devices.fortigate import (
        FortiGateDriver,
    )

    warnings = FortiGateDriver._assert_cli_success("config system interface\\nend")

    assert warnings == ()
