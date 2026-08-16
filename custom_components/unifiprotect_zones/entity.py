"""Shared entity plumbing for the UniFi Protect Zone Tracking integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from uiprotect.data import Camera

from .const import SIGNAL_ZONE_EVENT
from .hub import ProtectZoneHub, ZoneActivity


class ProtectZoneEntity(Entity):
    """Base for every entity fed by one camera's zone activity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: ProtectZoneHub, camera: Camera) -> None:
        self._hub = hub
        self._camera_id = camera.id
        # Sharing the connection with the core `unifiprotect` integration's
        # device merges these entities onto the same camera device instead of
        # creating a second one.
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, camera.mac)},
            name=camera.name or camera.id,
        )

    async def async_added_to_hass(self) -> None:
        """Listen for zone activity on this entity's camera."""
        await super().async_added_to_hass()
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
        """Handle one processed smart-detect event."""
        raise NotImplementedError
