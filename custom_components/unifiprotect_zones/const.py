"""Constants for the UniFi Protect Zone Tracking integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "unifiprotect_zones"

PLATFORMS: Final = ["binary_sensor", "event", "sensor"]

CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_AUTO_OFF_SECONDS: Final = "auto_off_seconds"

DEFAULT_PORT: Final = 443
DEFAULT_VERIFY_SSL: Final = False
# Protect only reports a smart-detect track once the event has finished, so
# the per-zone binary sensors are pulses: they switch on when the event is
# processed and back off after this many seconds.
DEFAULT_AUTO_OFF_SECONDS: Final = 10
MIN_AUTO_OFF_SECONDS: Final = 1
MAX_AUTO_OFF_SECONDS: Final = 3600

EVENT_TYPE_ZONE_ACTIVITY: Final = "zone_activity"

# Object types that get their own per-zone entity. The values are the ones
# UniFi Protect uses in its API.
OBJECT_TYPE_PERSON: Final = "person"
OBJECT_TYPE_VEHICLE: Final = "vehicle"
OBJECT_TYPE_ANIMAL: Final = "animal"
OBJECT_TYPE_LICENSE_PLATE: Final = "licensePlate"

ZONE_OBJECT_TYPES: Final = (
    OBJECT_TYPE_PERSON,
    OBJECT_TYPE_VEHICLE,
    OBJECT_TYPE_ANIMAL,
    OBJECT_TYPE_LICENSE_PLATE,
)

# Protect uses a couple of near-synonyms depending on firmware and on where
# in the API the value shows up; they are folded into the four types above.
OBJECT_TYPE_ALIASES: Final = {
    "pet": OBJECT_TYPE_ANIMAL,
    "car": OBJECT_TYPE_VEHICLE,
}

# Used to build unique ids and entity ids, so it must stay stable.
OBJECT_TYPE_SLUGS: Final = {
    OBJECT_TYPE_PERSON: "person",
    OBJECT_TYPE_VEHICLE: "vehicle",
    OBJECT_TYPE_ANIMAL: "animal",
    OBJECT_TYPE_LICENSE_PLATE: "license_plate",
}

# Object types that can carry a license plate. Protect only ever reads a
# plate off a vehicle, and reports it either on the vehicle track point or as
# a separate licensePlate detection for the same event.
PLATE_CARRIER_TYPES: Final = frozenset({OBJECT_TYPE_VEHICLE, OBJECT_TYPE_LICENSE_PLATE})

# Where a per-zone plate reading came from: read on a track point that was
# inside the zone, or taken from the event as a whole (see
# `build_zone_activity`).
PLATE_SOURCE_ZONE: Final = "zone"
PLATE_SOURCE_EVENT: Final = "event"

# Keys in strings.json / translations/*.json.
OBJECT_TYPE_TRANSLATION_KEYS: Final = {
    OBJECT_TYPE_PERSON: "zone_person",
    OBJECT_TYPE_VEHICLE: "zone_vehicle",
    OBJECT_TYPE_ANIMAL: "zone_animal",
    OBJECT_TYPE_LICENSE_PLATE: "zone_license_plate",
}

# Dispatcher signal for one processed event, formatted with the config
# entry_id and the Protect camera id.
SIGNAL_ZONE_EVENT: Final = f"{DOMAIN}_zone_event_{{entry_id}}_{{camera_id}}"
# Dispatcher signal telling the platforms that a camera's Smart Detection
# Zones may have changed, so entities for newly added zones can be created.
SIGNAL_ZONES_UPDATED: Final = f"{DOMAIN}_zones_updated_{{entry_id}}"


def normalize_object_type(object_type: str) -> str:
    """Fold Protect's object-type synonyms onto the types we track."""
    return OBJECT_TYPE_ALIASES.get(object_type, object_type)
