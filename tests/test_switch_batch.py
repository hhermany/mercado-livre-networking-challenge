import pytest

from src.switch.batch import (
    build_batch_preview,
    build_selection_preview,
    combine_interface_selection,
    select_interface_range,
    select_specific_interfaces,
)

INTERFACES = [
    {
        "name": "Gi0/0",
        "description": "",
        "status": "connected",
        "status_label": "Up",
        "vlan": "routed",
        "mode_label": "Routed",
    },
    {
        "name": "Gi0/1",
        "description": "HOST DE TESTES",
        "status": "connected",
        "status_label": "Up",
        "vlan": "10",
        "mode_label": "VLAN 10",
    },
    {
        "name": "Gi0/2",
        "description": "",
        "status": "notconnect",
        "status_label": "Not Connected",
        "vlan": "1",
        "mode_label": "VLAN 1",
    },
    {
        "name": "Gi0/3",
        "description": "",
        "status": "disabled",
        "status_label": "Admin Down",
        "vlan": "1",
        "mode_label": "VLAN 1",
    },
]


def test_selects_inclusive_interface_range():
    selected = select_interface_range(
        interfaces=INTERFACES,
        start_interface="Gi0/1",
        end_interface="Gi0/3",
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/1",
        "Gi0/2",
        "Gi0/3",
    ]


def test_allows_single_interface_range():
    selected = select_interface_range(
        interfaces=INTERFACES,
        start_interface="Gi0/2",
        end_interface="Gi0/2",
    )

    assert len(selected) == 1
    assert selected[0]["name"] == "Gi0/2"


def test_preserves_device_inventory_order():
    selected = select_interface_range(
        interfaces=INTERFACES,
        start_interface="Gi0/0",
        end_interface="Gi0/2",
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/0",
        "Gi0/1",
        "Gi0/2",
    ]


def test_rejects_unknown_start_interface():
    with pytest.raises(
        ValueError,
        match="interface inicial",
    ):
        select_interface_range(
            interfaces=INTERFACES,
            start_interface="Gi99/0",
            end_interface="Gi0/3",
        )


def test_rejects_unknown_end_interface():
    with pytest.raises(
        ValueError,
        match="interface final",
    ):
        select_interface_range(
            interfaces=INTERFACES,
            start_interface="Gi0/1",
            end_interface="Gi99/0",
        )


def test_rejects_reverse_range():
    with pytest.raises(
        ValueError,
        match="deve aparecer antes",
    ):
        select_interface_range(
            interfaces=INTERFACES,
            start_interface="Gi0/3",
            end_interface="Gi0/1",
        )


def test_requires_both_range_limits():
    with pytest.raises(
        ValueError,
        match="inicial e a interface final",
    ):
        select_interface_range(
            interfaces=INTERFACES,
            start_interface="Gi0/1",
            end_interface="",
        )


def test_preview_reports_total_interfaces():
    preview = build_batch_preview(
        interfaces=INTERFACES,
        start_interface="Gi0/1",
        end_interface="Gi0/3",
    )

    assert preview["count"] == 3
    assert preview["start_interface"] == "Gi0/1"
    assert preview["end_interface"] == "Gi0/3"


def test_preview_warns_about_connected_interface():
    preview = build_batch_preview(
        interfaces=INTERFACES,
        start_interface="Gi0/1",
        end_interface="Gi0/2",
    )

    gi01 = preview["interfaces"][0]

    assert "Interface está conectada" in gi01["warnings"]


def test_preview_warns_about_existing_description():
    preview = build_batch_preview(
        interfaces=INTERFACES,
        start_interface="Gi0/1",
        end_interface="Gi0/1",
    )

    gi01 = preview["interfaces"][0]

    assert "Interface possui descrição" in gi01["warnings"]


def test_preview_warns_about_routed_interface():
    preview = build_batch_preview(
        interfaces=INTERFACES,
        start_interface="Gi0/0",
        end_interface="Gi0/1",
    )

    gi00 = preview["interfaces"][0]

    assert "Interface Layer 3 (routed)" in gi00["warnings"]


def test_preview_marks_clean_range_without_warnings():
    interfaces = [
        {
            "name": "Gi1/0/1",
            "description": "",
            "status": "notconnect",
            "status_label": "Not Connected",
            "vlan": "1",
            "mode_label": "VLAN 1",
        },
        {
            "name": "Gi1/0/2",
            "description": "",
            "status": "notconnect",
            "status_label": "Not Connected",
            "vlan": "1",
            "mode_label": "VLAN 1",
        },
    ]

    preview = build_batch_preview(
        interfaces=interfaces,
        start_interface="Gi1/0/1",
        end_interface="Gi1/0/2",
    )

    assert preview["has_warnings"] is False


def test_selects_specific_non_contiguous_interfaces():
    selected = select_specific_interfaces(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/1",
            "Gi0/3",
        ],
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/1",
        "Gi0/3",
    ]


def test_combines_range_and_specific_interfaces():
    selected = combine_interface_selection(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/3",
        ],
        start_interface="Gi0/0",
        end_interface="Gi0/2",
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/0",
        "Gi0/1",
        "Gi0/2",
        "Gi0/3",
    ]


def test_combined_selection_removes_duplicates():
    selected = combine_interface_selection(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/1",
            "Gi0/3",
        ],
        start_interface="Gi0/0",
        end_interface="Gi0/2",
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/0",
        "Gi0/1",
        "Gi0/2",
        "Gi0/3",
    ]


def test_combined_selection_preserves_inventory_order():
    selected = combine_interface_selection(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/3",
            "Gi0/1",
        ],
    )

    assert [
        item["name"]
        for item in selected
    ] == [
        "Gi0/1",
        "Gi0/3",
    ]


def test_combined_selection_requires_something_selected():
    with pytest.raises(
        ValueError,
        match="Selecione pelo menos uma interface",
    ):
        combine_interface_selection(
            interfaces=INTERFACES,
        )


def test_combined_selection_requires_complete_range():
    with pytest.raises(
        ValueError,
        match="interface inicial",
    ):
        combine_interface_selection(
            interfaces=INTERFACES,
            start_interface="Gi0/1",
        )


def test_combined_selection_rejects_unknown_checkbox_interface():
    with pytest.raises(
        ValueError,
        match="não encontradas",
    ):
        combine_interface_selection(
            interfaces=INTERFACES,
            selected_names=[
                "Gi99/99",
            ],
        )


def test_selection_preview_lists_exact_interfaces():
    preview = build_selection_preview(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/3",
        ],
        start_interface="Gi0/1",
        end_interface="Gi0/2",
    )

    assert preview["count"] == 3

    assert preview["names"] == [
        "Gi0/1",
        "Gi0/2",
        "Gi0/3",
    ]


def test_selection_preview_keeps_warnings():
    preview = build_selection_preview(
        interfaces=INTERFACES,
        selected_names=[
            "Gi0/0",
            "Gi0/1",
        ],
    )

    assert preview["has_warnings"] is True

    assert (
        "Interface Layer 3 (routed)"
        in preview["interfaces"][0]["warnings"]
    )
