# Changelog

All notable changes to this project are documented here. This project uses
[semantic versioning](https://semver.org/); the version in
`custom_components/unifiprotect_zones/manifest.json` is what HACS and Home
Assistant read.

## 0.3.0

### Added

- `sensor.<camera>_<zone>_license_plate_number` for every zone that detects
  vehicles: the **state is the recognized plate text**, so the current plate
  per zone is visible on a dashboard and usable in templates without digging
  through attributes. It keeps its last value (also across restarts) instead
  of pulsing, and carries `zone`, `license_plates`, `license_plate_source`,
  `event_id` and `last_detected` as attributes.
- Plates are now also read from the event's own detection metadata, not just
  from the smart-detect track points, so a plate Protect reports only at
  event level is no longer lost.
- When an event contains exactly one plate, that plate is attributed to every
  zone that saw a vehicle (`license_plate_source: event`) - Protect regularly
  reads the plate on a frame that carries no zone ids. Events with more than
  one plate are left unguessed.
- The event entity reports `license_plate` and `license_plates_by_zone`
  (zone name → plates); `sensor.<camera>_detected_object_type` gained the
  same two attributes.
- The per-zone license plate binary sensors gained `license_plate` (the most
  recent one) and `license_plate_source`.

## 0.2.0

### Added

- `sensor.<camera>_detected_object_type` and `sensor.<camera>_lines_crossed`
  per camera, so the object type and the crossed lines of the last zone
  activity are usable without unpacking an event. Both restore their value
  across a restart.
- Up to four binary sensors per camera *and zone* - person, vehicle, animal
  and license plate - that only turn on when that object type was really
  inside that zone. Only the object types a zone is configured for get an
  entity (plus license plate for zones that detect vehicles).
- Zones added in the Protect app show up as entities without a reload.
- An options flow to configure how long the per-zone binary sensors stay on
  (default 10 seconds).
- The event entity now also reports `zones`, `object_types` and
  `license_plates`.
- Entity names are translated (English, German).
- GitHub workflow running hassfest, HACS validation and ruff.

### Fixed

- Crossed lines were resolved against the *zone* name table, so a line could
  be reported under an unrelated zone's name. Protect does not expose line
  names at all, so lines are now reported as `line-<id>`.

### Changed

- Minimum Home Assistant version is 2025.1.0.
- The integration stores its runtime state on the config entry
  (`entry.runtime_data`) instead of `hass.data`.

## 0.1.0

- Initial release: one `event.<camera>_zone_activity` entity per camera with
  the ordered zone path of each finished smart-detect event.
