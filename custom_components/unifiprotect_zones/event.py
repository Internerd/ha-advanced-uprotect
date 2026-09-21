"""Event entities exposing UniFi Protect smart-detect zone paths."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from uiprotect.data import Camera

from .const import EVENT_TYPE_ZONE_ACTIVITY, SIGNAL_ZONES_UPDATED
from .entity import ProtectZoneEntity
from .hub import (
    ProtectZoneHub,
    ProtectZonesConfigEntry,
    ZoneActivity,
    camera_reports_zones,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one event entity per camera that can report zone activity.

    A camera qualifies the moment its first Smart Detection Zone is drawn,
    which can happen long after setup, so the platform also listens for zone
    changes instead of only looking at the cameras present at startup.
    """
    hub = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_camera(camera: Camera) -> None:
        if camera.id in known or not camera_reports_zones(camera):
            return
        known.add(camera.id)
        async_add_entities([ProtectZoneEventEntity(hub, camera)])

    @callback
    def _async_zones_updated(camera_id: str) -> None:
        if (camera := hub.get_camera(camera_id)) is not None:
            _async_add_camera(camera)

    for camera in hub.cameras:
        _async_add_camera(camera)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_ZONES_UPDATED.format(entry_id=entry.entry_id),
            _async_zones_updated,
        )
    )


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
                "object_types_by_zone": {
                    detection.zone_name: detection.object_type_list
                    for detection in activity.detections_by_zone.values()
                },
                "license_plate": activity.license_plate,
                "license_plates": activity.license_plates,
                "license_plates_by_zone": {
                    detection.zone_name: detection.license_plates
                    for detection in activity.detections_by_zone.values()
                    if detection.license_plates
                },
            },
        )
        self.async_write_ha_state()
