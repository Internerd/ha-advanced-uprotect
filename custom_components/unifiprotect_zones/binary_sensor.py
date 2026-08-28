"""Per-zone binary sensors: which object type was seen in which zone."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util
from uiprotect.data import Camera
from uiprotect.data.devices import SmartMotionZone

from .const import (
    CONF_AUTO_OFF_SECONDS,
    DEFAULT_AUTO_OFF_SECONDS,
    OBJECT_TYPE_ANY,
    OBJECT_TYPE_LICENSE_PLATE,
    OBJECT_TYPE_SLUGS,
    OBJECT_TYPE_TRANSLATION_KEYS,
    SIGNAL_ZONES_UPDATED,
)
from .entity import ProtectZoneEntity
from .hub import (
    ProtectZoneHub,
    ProtectZonesConfigEntry,
    ZoneActivity,
    zone_object_types,
)

_ICONS = {OBJECT_TYPE_LICENSE_PLATE: "mdi:car-license-plate"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProtectZonesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one entity per camera, zone and detectable object type.

    Every zone additionally gets the type-agnostic "activity" sensor, which
    is the closest the Protect API gets to plain motion per zone.

    Zones can be added in the Protect app at any time, so the platform keeps
    track of what it has already created and adds entities for zones as they
    show up.
    """
    hub = entry.runtime_data
    auto_off = entry.options.get(CONF_AUTO_OFF_SECONDS, DEFAULT_AUTO_OFF_SECONDS)
    known: set[tuple[str, int, str]] = set()

    @callback
    def _async_add_camera_zones(camera: Camera) -> None:
        entities: list[ProtectZoneObjectBinarySensor] = []
        for zone in camera.smart_detect_zones:
            for object_type in (OBJECT_TYPE_ANY, *zone_object_types(zone)):
                key = (camera.id, zone.id, object_type)
                if key in known:
                    continue
                known.add(key)
                entities.append(
                    ProtectZoneObjectBinarySensor(
                        hub, camera, zone, object_type, auto_off
                    )
                )
        if entities:
            async_add_entities(entities)

    @callback
    def _async_zones_updated(camera_id: str) -> None:
        if (camera := hub.get_camera(camera_id)) is not None:
            _async_add_camera_zones(camera)

    for camera in hub.cameras:
        _async_add_camera_zones(camera)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_ZONES_UPDATED.format(entry_id=entry.entry_id),
            _async_zones_updated,
        )
    )


class ProtectZoneObjectBinarySensor(ProtectZoneEntity, BinarySensorEntity):
    """Turns on when a given object type was tracked inside a given zone.

    With :data:`OBJECT_TYPE_ANY` it turns on for *any* tracked object in that
    zone instead, including object types that have no entity of their own.

    Protect only hands out a smart-detect track once the event has finished,
    so this is a pulse: it switches on when the event is processed and back
    off after the configured delay.
    """

    def __init__(
        self,
        hub: ProtectZoneHub,
        camera: Camera,
        zone: SmartMotionZone,
        object_type: str,
        auto_off_seconds: int,
    ) -> None:
        super().__init__(hub, camera)
        self._zone_id = zone.id
        self._zone_name = zone.name
        self._object_type = object_type
        self._auto_off_seconds = auto_off_seconds
        self._unsub_auto_off: Callable[[], None] | None = None
        self._attr_is_on = False
        self._attr_translation_key = OBJECT_TYPE_TRANSLATION_KEYS[object_type]
        self._attr_translation_placeholders = {"zone": zone.name}
        self._attr_unique_id = (
            f"{hub.entry_id}_{camera.id}_zone_{zone.id}"
            f"_{OBJECT_TYPE_SLUGS[object_type]}"
        )
        if object_type in _ICONS:
            self._attr_icon = _ICONS[object_type]
        else:
            self._attr_device_class = BinarySensorDeviceClass.MOTION
        self._last_detected: datetime | None = None
        self._last_event_id: str | None = None
        self._detected_object_types: list[str] = []
        self._license_plates: list[str] = []
        self._license_plate_source: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "zone": self._zone_name,
            "object_type": self._object_type,
            "event_id": self._last_event_id,
            "last_detected": self._last_detected.isoformat()
            if self._last_detected
            else None,
        }
        if self._object_type == OBJECT_TYPE_ANY:
            # What the zone-agnostic sensor actually reacted to.
            attributes["object_types"] = self._detected_object_types
        if self._object_type == OBJECT_TYPE_LICENSE_PLATE:
            attributes["license_plate"] = (
                self._license_plates[-1] if self._license_plates else None
            )
            attributes["license_plates"] = self._license_plates
            attributes["license_plate_source"] = self._license_plate_source
        return attributes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._async_cancel_auto_off)

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        detection = activity.detections_by_zone.get(self._zone_id)
        if detection is None:
            return
        if (
            self._object_type != OBJECT_TYPE_ANY
            and self._object_type not in detection.object_types
        ):
            return

        self._last_event_id = activity.event_id
        self._last_detected = dt_util.utcnow()
        self._detected_object_types = detection.object_type_list
        self._license_plates = list(detection.license_plates)
        self._license_plate_source = detection.license_plate_source
        self._attr_is_on = True
        self._async_cancel_auto_off()
        self._unsub_auto_off = async_call_later(
            self.hass, self._auto_off_seconds, self._async_auto_off
        )
        self.async_write_ha_state()

    @callback
    def _async_auto_off(self, _now: datetime) -> None:
        self._unsub_auto_off = None
        self._attr_is_on = False
        self.async_write_ha_state()

    @callback
    def _async_cancel_auto_off(self) -> None:
        if self._unsub_auto_off is not None:
            self._unsub_auto_off()
            self._unsub_auto_off = None
