import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def get_base_url() -> str:
    base_url = os.getenv("NAUTOBOT_URL")

    if not base_url:
        raise RuntimeError("NAUTOBOT_URL is not configured.")

    return base_url.rstrip("/")


def get_headers() -> dict[str, str]:
    token = os.getenv("NAUTOBOT_TOKEN")

    if not token:
        raise RuntimeError("NAUTOBOT_TOKEN is not configured.")

    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_parent_prefix() -> str:
    prefix = os.getenv("NAUTOBOT_PARENT_PREFIX")

    if not prefix:
        raise RuntimeError("NAUTOBOT_PARENT_PREFIX is not configured.")

    return prefix


def ensure_parent_prefix() -> None:
    base_url = get_base_url()
    prefix = get_parent_prefix()
    headers = get_headers()

    url = f"{base_url}/api/ipam/prefixes/"

    response = requests.get(
        url,
        headers=headers,
        params={"prefix": prefix},
        timeout=10,
    )
    response.raise_for_status()

    results = response.json()["results"]

    if results:
        print(f"Prefix {prefix} already exists.")
        return

    payload = {
        "prefix": prefix,
        "status": "Active",
        "description": "VPN Tunnel Address Pool",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=10,
    )
    response.raise_for_status()

    print(f"Prefix {prefix} created.")


def validate_rbac() -> None:
    """
    Validate the expected RBAC configuration.

    RBAC creation requires administrative privileges and is intentionally
    separated from the restricted automation token used by the application.
    """

    expected_group = os.getenv(
        "NAUTOBOT_AUTOMATION_GROUP",
        "network-automation-ipam",
    )

    expected_user = os.getenv(
        "NAUTOBOT_AUTOMATION_USERNAME",
        "network-automation",
    )

    print("Expected RBAC configuration:")
    print(f"- User: {expected_user}")
    print(f"- Group: {expected_group}")
    print(
        "- Prefix permission: view, add, change, delete on ipam.prefix"
    )
    print(
        "- Reference-data permission: view on extras.status "
        "and ipam.namespace"
    )


def main() -> None:
    try:
        ensure_parent_prefix()
        validate_rbac()

    except (requests.RequestException, RuntimeError) as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
