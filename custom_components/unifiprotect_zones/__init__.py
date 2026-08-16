"""The UniFi Protect Zone Tracking integration.

Runs alongside the official ``unifiprotect`` core integration. It opens its
own connection to the same Protect NVR purely to derive the zone-path of
each smart-detect event (which zones - and in which order - an object moved
through, and which object was in which zone), data the core integration does
not expose.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from uiprotect.exceptions import ClientError, NotAuthorized

from .const import CONF_VERIFY_SSL, PLATFORMS
from .hub import ProtectZoneHub, ProtectZonesConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: ProtectZonesConfigEntry
) -> bool:
    hub = ProtectZoneHub(
        hass=hass,
        entry_id=entry.entry_id,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify_ssl=entry.data[CONF_VERIFY_SSL],
    )

    try:
        await hub.async_connect()
    except NotAuthorized as err:
        raise ConfigEntryNotReady(
            f"Invalid credentials for Protect NVR: {err}"
        ) from err
    except ClientError as err:
        raise ConfigEntryNotReady(f"Could not reach Protect NVR: {err}") from err

    entry.runtime_data = hub
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ProtectZonesConfigEntry
) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_disconnect()
    return unload_ok


async def _async_options_updated(
    hass: HomeAssistant, entry: ProtectZonesConfigEntry
) -> None:
    """Reload so entities pick up a changed auto-off delay."""
    await hass.config_entries.async_reload(entry.entry_id)
