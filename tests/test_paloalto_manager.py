from src.devices.paloalto_manager import PaloAltoManager

PA_OUTPUT = """\
crypto-profiles {
  ike-crypto-profiles {
    default {
      encryption [ aes-128-cbc 3des];
      hash sha1;
      dh-group group2;
    }
    IKE-FGT-PA {
      hash sha256;
      dh-group group14;
      lifetime {
        hours 8;
      }
      encryption des;
    }
  }
  ipsec-crypto-profiles {
    default {
      esp {
        encryption [ aes-128-cbc 3des];
        authentication sha1;
      }
      dh-group group2;
    }
    IPSEC-FGT-PA {
      esp {
        authentication sha256;
        encryption des;
      }
      dh-group group14;
      lifetime {
        hours 1;
      }
    }
  }
}
"""


def test_parse_real_lab_crypto_profiles():
    result = PaloAltoManager.parse_crypto_profiles(PA_OUTPUT)

    assert result.ike_versions == ()
    assert result.phase1_proposals == ("des-sha256",)
    assert result.phase1_dh_groups == (14,)
    assert result.phase2_proposals == ("des-sha256",)
    assert result.phase2_dh_groups == (14,)


def test_parser_uses_named_profiles_only():
    result = PaloAltoManager.parse_crypto_profiles(
        PA_OUTPUT,
        ike_profile="IKE-FGT-PA",
        ipsec_profile="IPSEC-FGT-PA",
    )

    assert "aes-128-cbc-sha1" not in (result.phase1_proposals)


def test_missing_profile_fails_closed():
    try:
        PaloAltoManager.parse_crypto_profiles(
            PA_OUTPUT,
            ike_profile="PROFILE-QUE-NAO-EXISTE",
        )
    except ValueError as exc:
        assert "nao encontrado" in str(exc)
    else:
        raise AssertionError("Parser deveria falhar sem profile.")


PA_IKE_GATEWAYS = """\
gateway {
  IKE-GW-FGT {
    protocol {
      ikev2 {
        ike-crypto-profile IKE-FGT-PA;
      }
      version ikev2;
    }
  }
  IKE-GW-FGT2 {
    protocol {
      ikev2 {
        ike-crypto-profile IKE-FGT-PA;
      }
      version ikev2;
    }
  }
}
"""


def test_parse_real_lab_ike_version():
    assert PaloAltoManager.parse_ike_versions(PA_IKE_GATEWAYS) == (2,)


def test_parse_ike_versions_deduplicates_gateways():
    output = """\
gateway {
  ONE {
    protocol {
      version ikev2;
    }
  }
  TWO {
    protocol {
      version ikev2;
    }
  }
}
"""

    assert PaloAltoManager.parse_ike_versions(output) == (2,)


def test_parse_ike_versions_fails_closed():
    try:
        PaloAltoManager.parse_ike_versions("gateway { TEST { } }")
    except ValueError as exc:
        assert "Nenhuma versao IKE" in str(exc)
    else:
        raise AssertionError("Parser deveria falhar sem versao IKE.")
