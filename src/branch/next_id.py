import os
import re

import requests
from dotenv import load_dotenv

load_dotenv(".env")


def get_next_branch_id() -> int:
    base = os.environ["NAUTOBOT_URL"].rstrip("/")
    token = os.environ["NAUTOBOT_TOKEN"]

    headers = {
        "Authorization": f"Token {token}",
    }

    response = requests.get(
        f"{base}/api/ipam/prefixes/",
        headers=headers,
        params={"limit": 1000},
        timeout=10,
    )
    response.raise_for_status()

    ids = set()

    for prefix in response.json()["results"]:
        description = prefix.get("description", "")

        match = re.match(r"BRANCH-(\d+)\s", description)

        if match:
            ids.add(int(match.group(1)))

    branch_id = 1

    while branch_id in ids:
        branch_id += 1

    return branch_id
