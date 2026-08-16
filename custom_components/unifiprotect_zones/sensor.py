"""Per-camera sensors for the last smart-detect object type and crossed lines."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from uiprotect.data import Camera

from .entity import ProtectZoneEntity
from .hub import ProtectZoneHub, ProtectZonesConfigEntry, ZoneActivity

# Home Assistant rejects states longer than this.
MAX_STATE_LENGTH = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    entities: list[SensorEntity] = []
    for camera in hub.cameras:
        entities.append(ProtectObjectTypeSensor(hub, camera))
        entities.append(ProtectLinesCrossedSensor(hub, camera))
    async_add_entities(entities)


def _fit_state(value: str) -> str:
    """Keep a joined list inside Home Assistant's state length limit."""
    if len(value) <= MAX_STATE_LENGTH:
        return value
    return f"{value[: MAX_STATE_LENGTH - 1]}…"


class ProtectZoneSensorBase(ProtectZoneEntity, RestoreEntity, SensorEntity):
    """Sensor that keeps its last value across restarts."""

    _restored_attributes: ClassVar[set[str]]

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        super().__init__(hub, camera)
        self._attr_extra_state_attributes = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is None:
            return
        if last_state.state in (None, "unknown", "unavailable"):
            return
        self._attr_native_value = last_state.state
        self._attr_extra_state_attributes = {
            key: value
            for key, value in last_state.attributes.items()
            if key in self._restored_attributes
        }


class ProtectObjectTypeSensor(ProtectZoneSensorBase):
    """The object type of the most recent zone-relevant detection."""

    _attr_translation_key = "object_type"
    _attr_icon = "mdi:shape-outline"
    _restored_attributes: ClassVar[set[str]] = {
        "object_types",
        "event_id",
        "zones",
        "license_plates",
    }

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        super().__init__(hub, camera)
        self._attr_unique_id = f"{hub.entry_id}_{camera.id}_object_type"

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        self._attr_native_value = activity.object_type
        self._attr_extra_state_attributes = {
            "object_types": activity.object_types,
            "event_id": activity.event_id,
            "zones": activity.zones,
            "license_plates": activity.license_plates,
        }
        self.async_write_ha_state()


class ProtectLinesCrossedSensor(ProtectZoneSensorBase):
    """The line-crossing zone(s) the most recent tracked object touched."""

    _attr_translation_key = "lines_crossed"
    _attr_icon = "mdi:vector-line"
    _restored_attributes: ClassVar[set[str]] = {
        "lines_crossed",
        "line_count",
        "event_id",
        "object_type",
    }

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        super().__init__(hub, camera)
        self._attr_unique_id = f"{hub.entry_id}_{camera.id}_lines_crossed"

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        # Events that stayed inside zones without touching a line would
        # otherwise clear a perfectly good previous value.
        if not activity.lines_crossed:
            return
        self._attr_native_value = _fit_state(", ".join(activity.lines_crossed))
        self._attr_extra_state_attributes = {
            "lines_crossed": activity.lines_crossed,
            "line_count": len(activity.lines_crossed),
            "event_id": activity.event_id,
            "object_type": activity.object_type,
        }
        self.async_write_ha_state()
