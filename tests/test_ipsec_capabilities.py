import pytest

from src.vpn.capabilities import (
    IPsecCapabilities,
    intersect_capabilities,
    validate_selected_capabilities,
)


def test_intersection_keeps_only_common_values():
    fortigate = IPsecCapabilities(
        ike_versions=(1, 2),
        phase1_proposals=(
            "des-sha1",
            "des-sha256",
            "des-sha384",
        ),
        phase1_dh_groups=(
            5,
            14,
            19,
        ),
        phase2_proposals=(
            "des-sha1",
            "des-sha256",
        ),
        phase2_dh_groups=(
            5,
            14,
        ),
    )

    paloalto = IPsecCapabilities(
        ike_versions=(2,),
        phase1_proposals=(
            "aes256-sha256",
            "des-sha256",
        ),
        phase1_dh_groups=(
            14,
            20,
        ),
        phase2_proposals=(
            "des-sha256",
            "aes128-sha256",
        ),
        phase2_dh_groups=(
            14,
            19,
        ),
    )

    result = intersect_capabilities(
        fortigate,
        paloalto,
    )

    assert result.ike_versions == (2,)
    assert result.phase1_proposals == ("des-sha256",)
    assert result.phase1_dh_groups == (14,)
    assert result.phase2_proposals == ("des-sha256",)
    assert result.phase2_dh_groups == (14,)


def test_validation_rejects_non_common_value():
    supported = IPsecCapabilities(
        ike_versions=(2,),
        phase1_proposals=("des-sha256",),
        phase1_dh_groups=(14,),
        phase2_proposals=("des-sha256",),
        phase2_dh_groups=(14,),
    )

    selected = IPsecCapabilities(
        ike_versions=(2,),
        phase1_proposals=("aes256-sha256",),
        phase1_dh_groups=(14,),
        phase2_proposals=("des-sha256",),
        phase2_dh_groups=(14,),
    )

    with pytest.raises(
        ValueError,
        match="Phase1 Proposal",
    ):
        validate_selected_capabilities(
            selected=selected,
            supported=supported,
        )
