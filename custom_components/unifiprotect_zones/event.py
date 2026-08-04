"""Event entities exposing UniFi Protect smart-detect zone paths."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_TYPE_ZONE_ACTIVITY, SIGNAL_ZONE_EVENT
from .hub import ProtectZoneHub, ZoneActivity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub: ProtectZoneHub = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ProtectZoneEventEntity(hub, camera.id, camera.name or camera.id, camera.mac)
        for camera in hub.api.bootstrap.cameras.values()
        if camera.smart_detect_zones
    ]
    async_add_entities(entities)


class ProtectZoneEventEntity(EventEntity):
    """Fires whenever a finished smart-detect event touched a defined zone."""

    _attr_has_entity_name = True
    _attr_event_types = [EVENT_TYPE_ZONE_ACTIVITY]
    _attr_should_poll = False

    def __init__(
        self, hub: ProtectZoneHub, camera_id: str, camera_name: str, camera_mac: str
    ) -> None:
        self._hub = hub
        self._camera_id = camera_id
        self._attr_unique_id = f"{hub.entry_id}_{camera_id}_zone_activity"
        self._attr_name = "Zone activity"
        # Sharing the connection with the core `unifiprotect` integration's
        # device merges this entity onto the same camera device instead of
        # creating a second one.
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, camera_mac)},
            name=camera_name,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ZONE_EVENT.format(
                    entry_id=self._hub.entry_id, camera_id=self._camera_id
                ),
                self._async_handle_activity,
            )
        )

    @callback
    def _async_handle_activity(self, activity: ZoneActivity) -> None:
        self._trigger_event(
            EVENT_TYPE_ZONE_ACTIVITY,
            {
                "event_id": activity.event_id,
                "object_type": activity.object_type,
                "score": activity.score,
                "zone_path": activity.zone_path,
                "from_zone": activity.from_zone,
                "to_zone": activity.to_zone,
                "lines_crossed": activity.lines_crossed,
            },
        )
        self.async_write_ha_state()
