# UniFi Protect Zone Tracking

Custom Home Assistant integration that connects to a UniFi Protect NVR
*in addition to* the official core `unifiprotect` integration, purely to
expose one piece of data the core integration does not: **which Smart
Detection Zone(s) a person/vehicle/animal moved through during a single
detection event, in order.**

## Why a separate integration

The core integration exposes `binary_sensor`/`event` entities per detection
type (person, vehicle, ...) but not *where in the frame* the detection
happened. UniFi Protect's local API does have that data - it lives in the
per-event "smart detect track", which the NVR only keeps long enough to
answer one API call - but the core integration doesn't fetch or expose it.

This integration opens its own login session to the same NVR (Protect
supports multiple concurrent local sessions) and, for every finished
smart-detect event, fetches that track and resolves it against the
camera's configured zones.

## What you get

For every camera that has at least one Smart Detection Zone configured, a
`event.<camera>_zone_activity` entity is created. It fires once per
finished smart-detect event with these attributes:

| Attribute       | Meaning                                                                 |
|-----------------|--------------------------------------------------------------------------|
| `zone_path`     | Ordered, de-duplicated list of zone name(s) the object was in, step by step |
| `from_zone`     | First entry in `zone_path`                                             |
| `to_zone`       | Last entry in `zone_path`                                              |
| `lines_crossed` | Any line-crossing zones the object's track touched                      |
| `object_type`   | `person`, `vehicle`, `animal`, ...                                      |
| `score`         | Protect's detection confidence score                                   |
| `event_id`      | The Protect event id, for cross-referencing                            |

Use it in an automation trigger like any other `event` entity, e.g.
trigger on `event.einfahrt_zone_activity` and read
`trigger.event.data.from_zone` / `to_zone` in the action.

## Known limitation

UniFi Protect's *line-crossing* feature can report a crossing direction
(in/out) in its own web UI, but that direction is **not** modeled anywhere
in the local API data the `uiprotect` client library exposes (checked
against `uiprotect` 15.14.2) - only *which* line was crossed. `lines_crossed`
therefore lists the line(s) touched, but not the direction. If UniFi later
exposes that, `hub.py` is the only place that needs updating.

## Setup

**Via HACS:** HACS → Integrations → ⋮ → Custom repositories → add this repo
URL as an "Integration" → install "UniFi Protect Zone Tracking" → restart
Home Assistant.

**Manually:** copy `custom_components/unifiprotect_zones` into your Home
Assistant `config/custom_components/` folder and restart Home Assistant.

Then:

1. Settings → Devices & Services → Add Integration → "UniFi Protect Zone
   Tracking".
2. Enter the same NVR host, a Protect local user (a dedicated read-only
   local account is recommended over reusing the account the core
   integration uses), and whether to verify the NVR's SSL certificate
   (off by default for the typical self-signed local cert).
3. Configure Smart Detection Zones on the cameras you care about inside
   the Protect app itself, if you haven't already - this integration only
   reports on zones that already exist there.

Requires the `uiprotect` Python package (installed automatically from
`manifest.json`).
