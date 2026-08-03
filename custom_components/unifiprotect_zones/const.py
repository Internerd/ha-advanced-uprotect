"""Constants for the UniFi Protect Zone Tracking integration."""

DOMAIN = "unifiprotect_zones"

CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_PORT = 443
DEFAULT_VERIFY_SSL = False

EVENT_TYPE_ZONE_ACTIVITY = "zone_activity"

# Dispatcher signal, formatted with the config entry_id and the Protect camera id.
SIGNAL_ZONE_EVENT = f"{DOMAIN}_zone_event_{{entry_id}}_{{camera_id}}"
