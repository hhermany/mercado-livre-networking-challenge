import src.branch.next_id as next_id
from src.branch.next_id import get_next_branch_id


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "results": [
                {"description": "BRANCH-1 LAN"},
                {"description": "BRANCH-1 LO-MGMT"},
                {"description": "BRANCH-1 VPN1"},
                {"description": "BRANCH-1 VPN2"},
                {"description": "BRANCH-2 LAN"},
                {"description": "BRANCH-2 LO-MGMT"},
                {"description": "BRANCH-2 VPN1"},
                {"description": "BRANCH-2 VPN2"},
            ]
        }


def test_next_branch_id(monkeypatch):
    monkeypatch.setenv("NAUTOBOT_URL", "http://nautobot")
    monkeypatch.setenv("NAUTOBOT_TOKEN", "token")

    monkeypatch.setattr(
        next_id.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    assert next_id.get_next_branch_id() == 3


def test_next_branch_id_starts_at_two(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    monkeypatch.setattr(
        "src.branch.next_id.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )

    assert get_next_branch_id() == 2
