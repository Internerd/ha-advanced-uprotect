"""The UniFi Protect Zone Tracking integration.

Runs alongside the official ``unifiprotect`` core integration. It opens its
own connection to the same Protect NVR purely to derive the zone-path of
each smart-detect event (which zones - and in which order - an object moved
through), a field the core integration does not expose.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from uiprotect.exceptions import ClientError, NotAuthorized

from .const import CONF_VERIFY_SSL, DOMAIN
from .hub import ProtectZoneHub

PLATFORMS = ["event"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
        raise ConfigEntryNotReady(f"Invalid credentials for Protect NVR: {err}") from err
    except ClientError as err:
        raise ConfigEntryNotReady(f"Could not reach Protect NVR: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hub: ProtectZoneHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.async_disconnect()
    return unload_ok
