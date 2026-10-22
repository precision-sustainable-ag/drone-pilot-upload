"""Canonical organization and flight storage paths."""

from pathlib import Path
from uuid import UUID

from config import config


def validate_guid(value):
    """Return a normalized GUID or raise ValueError."""
    guid = str(UUID(str(value)))

    if guid != str(value):
        raise ValueError(f"Invalid GUID: {value}")

    return guid


def organization_id_for_alias(alias):
    """Resolve a registered organization alias to its permanent GUID."""

    if (
        not alias
        or alias in (".", "..")
        or "/" in alias
        or "\\" in alias
    ):
        raise ValueError("Invalid organization alias")

    root = Path(config["data_root"])
    id_root = (root / config["id_dir"]).resolve(strict=True)

    link = root / config["name_dir"] / alias

    if not link.is_symlink():
        raise ValueError(f"Unknown organization: {alias}")

    target = link.resolve(strict=True)

    # The alias must identify an immediate child of the GUID root.
    if target.parent != id_root or not target.is_dir():
        raise ValueError(f"Invalid organization target: {alias}")

    return validate_guid(target.name)


def flight_directory(organization_id, flight_id):
    """Return the canonical directory for a flight."""

    organization_id = validate_guid(organization_id)
    flight_id = validate_guid(flight_id)

    return str(
        Path(config["data_root"])
        / config["id_dir"]
        / organization_id
        / "flights"
        / flight_id
    )
