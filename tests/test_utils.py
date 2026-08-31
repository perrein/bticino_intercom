"""Unit tests for the BTicino utility helpers."""

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bticino_intercom.const import (
    DOMAIN,
    SUBTYPE_DOORLOCK,
    SUBTYPE_EXTERNAL_UNIT,
    SUBTYPE_STAIRCASE_LIGHT,
)
from custom_components.bticino_intercom.utils import (
    cleanup_orphaned_entities,
    resolve_module_subtype,
)


@pytest.mark.parametrize(
    ("module_data", "expected"),
    [
        # EOS (bridge BNCX): only the raw 'type' is present, no 'variant'.
        ({"type": "BNDL"}, SUBTYPE_DOORLOCK),
        ({"type": "BNSL"}, SUBTYPE_STAIRCASE_LIGHT),
        ({"type": "BNEU"}, SUBTYPE_EXTERNAL_UNIT),
        # Legacy 100X/300X: a redundant 'variant' yields the same subtype.
        ({"type": "BNDL", "variant": "BNDL:bndl_doorlock"}, SUBTYPE_DOORLOCK),
        ({"type": "BNSL", "variant": "BNSL:bnsl_staircase_light"}, SUBTYPE_STAIRCASE_LIGHT),
        ({"type": "BNEU", "variant": "BNEU:bneu_external_unit"}, SUBTYPE_EXTERNAL_UNIT),
        # Forward-compat override: an UNKNOWN variant subtype wins over the type.
        ({"type": "BNEU", "variant": "BNEU:bneu_future_thing"}, "bneu_future_thing"),
        # A malformed variant (no colon) is ignored — fall back to the type.
        ({"type": "BNDL", "variant": "garbage"}, SUBTYPE_DOORLOCK),
        # Bridge / unmapped type without a usable variant → None (no entity).
        ({"type": "BNCX"}, None),
        ({"type": "BNC1"}, None),
        # Bridge with a legacy (unknown) variant → its own subtype, matched by
        # no platform, so still no entity is created.
        ({"type": "BNC1", "variant": "BNC1:bnc1_bridge"}, "bnc1_bridge"),
        # Empty / missing data → None.
        ({}, None),
    ],
)
def test_resolve_module_subtype(module_data: dict, expected: str | None) -> None:
    """The type is canonical; variant only overrides for unknown subtypes."""
    assert resolve_module_subtype(module_data) == expected


@pytest.fixture
def registered_lock(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> er.RegistryEntry:
    """Register a lock entity as if created by a previous healthy setup."""
    mock_config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    return ent_reg.async_get_or_create(
        "lock",
        DOMAIN,
        f"{mock_config_entry.entry_id}_lock_module1",
        config_entry=mock_config_entry,
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_cleanup_removes_stale_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    registered_lock: er.RegistryEntry,
) -> None:
    """An entity whose unique_id is no longer built must be removed."""
    current = [MagicMock(unique_id=f"{mock_config_entry.entry_id}_lock_module2")]

    cleanup_orphaned_entities(hass, mock_config_entry.entry_id, "lock", current)

    assert er.async_get(hass).async_get(registered_lock.entity_id) is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_cleanup_keeps_current_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    registered_lock: er.RegistryEntry,
) -> None:
    """An entity rebuilt in the current setup pass must survive cleanup."""
    current = [MagicMock(unique_id=registered_lock.unique_id)]

    cleanup_orphaned_entities(hass, mock_config_entry.entry_id, "lock", current)

    assert er.async_get(hass).async_get(registered_lock.entity_id) is not None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_cleanup_skipped_when_no_entities_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    registered_lock: er.RegistryEntry,
) -> None:
    """Zero entities built means degraded cloud data, not module removal (issue #68).

    Cleanup must be skipped entirely so a transient empty/partial topology
    at startup cannot permanently delete the user's registered entities.
    """
    cleanup_orphaned_entities(hass, mock_config_entry.entry_id, "lock", [])

    assert er.async_get(hass).async_get(registered_lock.entity_id) is not None
