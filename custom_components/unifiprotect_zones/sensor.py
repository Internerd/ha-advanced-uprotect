"""Sensors for the last detected object type, crossed lines and plate per zone."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from uiprotect.data import Camera
from uiprotect.data.devices import SmartMotionZone

from .const import OBJECT_TYPE_LICENSE_PLATE, SIGNAL_ZONES_UPDATED
from .entity import ProtectZoneEntity
from .hub import (
    ProtectZoneHub,
    ProtectZonesConfigEntry,
    ZoneActivity,
    zone_object_types,
)

# Home Assistant rejects states longer than this.
MAX_STATE_LENGTH = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the per-camera sensors plus one plate sensor per plate zone.

    Zones can be added in the Protect app at any time, so - like the binary
    sensors - the platform tracks which zones it has already covered and adds
    entities for new ones as they show up.
    """
    hub = entry.runtime_data
    known_plate_zones: set[tuple[str, int]] = set()

    @callback
    def _async_add_plate_zones(camera: Camera) -> None:
        entities: list[SensorEntity] = []
        for zone in camera.smart_detect_zones:
            if OBJECT_TYPE_LICENSE_PLATE not in zone_object_types(zone):
                continue
            key = (camera.id, zone.id)
            if key in known_plate_zones:
                continue
            known_plate_zones.add(key)
            entities.append(ProtectZonePlateSensor(hub, camera, zone))
        if entities:
            async_add_entities(entities)

    @callback
    def _async_zones_updated(camera_id: str) -> None:
        if (camera := hub.get_camera(camera_id)) is not None:
            _async_add_plate_zones(camera)

    entities: list[SensorEntity] = []
    for camera in hub.cameras:
        entities.append(ProtectObjectTypeSensor(hub, camera))
        entities.append(ProtectLinesCrossedSensor(hub, camera))
    async_add_entities(entities)

    for camera in hub.cameras:
        _async_add_plate_zones(camera)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_ZONES_UPDATED.format(entry_id=entry.entry_id),
            _async_zones_updated,
        )
    )


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
        "object_types_by_zone",
        "event_id",
        "zones",
        "license_plate",
        "license_plates",
        "license_plates_by_zone",
    }

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        super().__init__(hub, camera)
        self._attr_unique_id = f"{hub.entry_id}_{camera.id}_object_type"

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        self._attr_native_value = activity.object_type
        self._attr_extra_state_attributes = {
            "object_types": activity.object_types,
            "object_types_by_zone": {
                detection.zone_name: detection.object_type_list
                for detection in activity.detections_by_zone.values()
            },
            "event_id": activity.event_id,
            "zones": activity.zones,
            "license_plate": activity.license_plate,
            "license_plates": activity.license_plates,
            "license_plates_by_zone": {
                detection.zone_name: detection.license_plates
                for detection in activity.detections_by_zone.values()
                if detection.license_plates
            },
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


class ProtectZonePlateSensor(ProtectZoneSensorBase):
    """The last license plate recognized inside one Smart Detection Zone.

    Unlike the per-zone binary sensors this is not a pulse: it keeps the last
    plate it saw (across restarts too), which is what makes it usable as a
    trigger value and as something to display on a dashboard.
    """

    _attr_translation_key = "zone_license_plate"
    _attr_icon = "mdi:car-license-plate"
    _restored_attributes: ClassVar[set[str]] = {
        "zone",
        "license_plates",
        "license_plate_source",
        "event_id",
        "last_detected",
    }

    def __init__(
        self, hub: ProtectZoneHub, camera: Camera, zone: SmartMotionZone
    ) -> None:
        super().__init__(hub, camera)
        self._zone_id = zone.id
        self._zone_name = zone.name
        self._attr_translation_placeholders = {"zone": zone.name}
        self._attr_unique_id = (
            f"{hub.entry_id}_{camera.id}_zone_{zone.id}_license_plate_number"
        )

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        detection = activity.detections_by_zone.get(self._zone_id)
        if detection is None or not detection.license_plates:
            # An event without a plate reading says nothing about this zone's
            # last known plate, so the previous value stays put.
            return

        self._attr_native_value = _fit_state(detection.license_plate or "")
        self._attr_extra_state_attributes = {
            "zone": self._zone_name,
            "license_plates": list(detection.license_plates),
            "license_plate_source": detection.license_plate_source,
            "event_id": activity.event_id,
            "last_detected": dt_util.utcnow().isoformat(),
        }
        self.async_write_ha_state()
