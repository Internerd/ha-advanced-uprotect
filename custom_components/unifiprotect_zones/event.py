"""Event entities exposing UniFi Protect smart-detect zone paths."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from uiprotect.data import Camera

from .const import EVENT_TYPE_ZONE_ACTIVITY
from .entity import ProtectZoneEntity
from .hub import ProtectZoneHub, ProtectZonesConfigEntry, ZoneActivity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    async_add_entities(ProtectZoneEventEntity(hub, camera) for camera in hub.cameras)


class ProtectZoneEventEntity(ProtectZoneEntity, EventEntity):
    """Fires whenever a finished smart-detect event touched a defined zone."""

    _attr_event_types: ClassVar[list[str]] = [EVENT_TYPE_ZONE_ACTIVITY]
    _attr_translation_key = "zone_activity"

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        super().__init__(hub, camera)
        self._attr_unique_id = f"{hub.entry_id}_{camera.id}_zone_activity"

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        self._trigger_event(
            EVENT_TYPE_ZONE_ACTIVITY,
            {
                "event_id": activity.event_id,
                "object_type": activity.object_type,
                "object_types": activity.object_types,
                "score": activity.score,
                "zone_path": activity.zone_path,
                "zones": activity.zones,
                "from_zone": activity.from_zone,
                "to_zone": activity.to_zone,
                "lines_crossed": activity.lines_crossed,
                "license_plates": activity.license_plates,
            },
        )
        self.async_write_ha_state()
