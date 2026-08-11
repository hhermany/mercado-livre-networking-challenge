import os

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from nautobot.users.models import ObjectPermission, User

GROUP_NAME = os.getenv(
    "NAUTOBOT_AUTOMATION_GROUP",
    "network-automation-ipam",
)

USERNAME = os.getenv(
    "NAUTOBOT_AUTOMATION_USERNAME",
    "network-automation",
)


def ensure_group() -> Group:
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    return group


def ensure_user(group: Group) -> User:
    user, _ = User.objects.get_or_create(
        username=USERNAME,
        defaults={
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
        },
    )

    user.groups.add(group)
    return user


def ensure_prefix_permission(group: Group) -> None:
    permission, _ = ObjectPermission.objects.get_or_create(
        name="network-automation-ipam-prefixes",
        defaults={
            "actions": ["view", "add", "change", "delete"],
        },
    )

    permission.actions = ["view", "add", "change", "delete"]
    permission.save()

    prefix_type = ContentType.objects.get(
        app_label="ipam",
        model="prefix",
    )

    permission.object_types.set([prefix_type])
    permission.groups.set([group])


def ensure_reference_permission(group: Group) -> None:
    permission, _ = ObjectPermission.objects.get_or_create(
        name="network-automation-ipam-reference-data",
        defaults={
            "actions": ["view"],
        },
    )

    permission.actions = ["view"]
    permission.save()

    status_type = ContentType.objects.get(
        app_label="extras",
        model="status",
    )

    namespace_type = ContentType.objects.get(
        app_label="ipam",
        model="namespace",
    )

    permission.object_types.set(
        [
            status_type,
            namespace_type,
        ]
    )

    permission.groups.set([group])


def main() -> None:
    group = ensure_group()
    ensure_user(group)
    ensure_prefix_permission(group)
    ensure_reference_permission(group)

    print("Nautobot RBAC bootstrap completed.")


if __name__ == "__main__":
    main()
