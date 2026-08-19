# UniFi Protect Zone Tracking

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Validate](https://github.com/Internerd/ha-advanced-uprotect/actions/workflows/validate.yml/badge.svg)](https://github.com/Internerd/ha-advanced-uprotect/actions/workflows/validate.yml)

*Unofficial, community-run project. Not affiliated with, supported by, or
endorsed by Ubiquiti Inc. "UniFi" and "UniFi Protect" are trademarks of
Ubiquiti Inc. - see the [Disclaimer](#disclaimer).*

Custom Home Assistant integration that connects to a UniFi Protect NVR
*in addition to* the official core `unifiprotect` integration, purely to
expose data the core integration does not: **which Smart Detection Zone(s)
a person, vehicle, animal or license plate moved through during a single
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

### One event entity per camera

For every camera that has at least one Smart Detection Zone (or line
crossing) configured, `event.<camera>_zone_activity` fires once per finished
smart-detect event that touched a zone or a line, with these attributes:

| Attribute        | Meaning                                                                    |
|------------------|----------------------------------------------------------------------------|
| `zone_path`      | Ordered, de-duplicated list of zone name(s) the object was in, step by step |
| `zones`          | Every zone the object touched, in the order it first entered them          |
| `from_zone`      | First entry in `zone_path`                                                 |
| `to_zone`        | Last entry in `zone_path`                                                  |
| `lines_crossed`  | Any line-crossing zones the object's track touched                         |
| `object_type`    | `person`, `vehicle`, `animal`, `licensePlate`, ...                         |
| `object_types`   | Every object type seen during the event                                    |
| `license_plate`  | The most recent license plate text read during the event                   |
| `license_plates` | Every license plate text read during the event                             |
| `license_plates_by_zone` | Mapping of zone name → the plate(s) read while the vehicle was in that zone |
| `score`          | Protect's detection confidence score                                       |
| `event_id`       | The Protect event id, for cross-referencing                                |

Use it in an automation trigger like any other `event` entity, e.g.
trigger on `event.driveway_zone_activity` and read
`trigger.event.data.from_zone` / `to_zone` in the action.

### Two extra sensors per camera

The two most useful attributes are also available as plain entities, so they
can be used in templates, dashboards and history without unpacking an event:

| Entity                                     | State                                                |
|--------------------------------------------|------------------------------------------------------|
| `sensor.<camera>_detected_object_type`     | Object type of the most recent zone activity         |
| `sensor.<camera>_lines_crossed`            | The line-crossing zone(s) the last track touched     |

Both keep the full detail in their attributes (`object_types`, `zones`,
`license_plate`, `license_plates`, `license_plates_by_zone`,
`lines_crossed`, `line_count`, `event_id`) and restore their last value
across a Home Assistant restart. `lines_crossed` only updates on events that
actually crossed a line, so a zone-only event does not wipe it.

### One license plate sensor per zone

For every Smart Detection Zone that detects vehicles, the integration also
creates a sensor whose **state is the plate text itself**:

| Entity                                                  | State                                        |
|---------------------------------------------------------|----------------------------------------------|
| `sensor.<camera>_<zone>_license_plate_number`            | Last plate recognized inside that zone, e.g. `M-AB 1234` |

Unlike the per-zone binary sensors this is not a pulse - it keeps the last
plate it saw (across restarts too), so it can be displayed on a dashboard
and compared in a template. Events without a plate reading leave the
previous value alone.

Attributes: `zone`, `license_plates` (all plates of the last event in that
zone), `license_plate_source`, `event_id`, `last_detected`.

**Where the plate comes from.** Protect reads a plate off a *vehicle*, and
reports it either on the individual track point (which carries the zone ids -
`license_plate_source: zone`) or only on the event as a whole
(`license_plate_source: event`). In the second case the plate is assigned to
every zone that saw a vehicle during that event, but **only when the whole
event contains exactly one plate**, so the assignment is unambiguous. If two
vehicles with two different plates appear in one event, each zone keeps only
the plate that was genuinely read while the vehicle was inside it - the rest
is left blank rather than guessed.

Example: notify with the plate that was seen in the driveway zone.

```yaml
automation:
  - alias: Announce plate in the driveway
    triggers:
      - trigger: state
        entity_id: sensor.driveway_cam_driveway_license_plate_number
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.state not in ['unknown', 'unavailable'] }}"
    actions:
      - action: notify.mobile_app
        data:
          message: "Vehicle {{ trigger.to_state.state }} in the driveway"
```

Protect's local API does not expose the *names* of crossing lines (only zone
names), so lines are reported by id as `line-<id>`.

### One binary sensor per camera, zone and object type

For every Smart Detection Zone the integration creates up to four binary
sensors:

| Entity                                          | Turns on when                              |
|-------------------------------------------------|--------------------------------------------|
| `binary_sensor.<camera>_<zone>_person`          | a person was tracked inside that zone      |
| `binary_sensor.<camera>_<zone>_vehicle`         | a vehicle was tracked inside that zone     |
| `binary_sensor.<camera>_<zone>_animal`          | an animal was tracked inside that zone     |
| `binary_sensor.<camera>_<zone>_license_plate`   | a license plate was read inside that zone  |

They only trigger when that object type was really inside that specific zone
during the event, which is exactly the distinction the core integration
cannot make.

A few notes on how they behave:

- **Only what the zone can detect.** Protect stores which object types a zone
  is configured for, and only those get an entity (plus license plate
  whenever the zone detects vehicles). A zone configured for people only
  therefore has a single entity, not four. Zones with no explicit
  configuration get all four.
- **They are pulses.** Protect publishes the detection track only after the
  event has ended, so a sensor switches on when the event is processed and
  off again after a delay you can configure (Settings → Devices & Services →
  UniFi Protect Zone Tracking → **Configure**; 10 seconds by default).
- **Zones added later are picked up automatically.** Add a zone in the
  Protect app and the matching entities appear without reloading anything.
  Renaming a zone updates the entity name after the next reload of the
  integration.
- **Attributes**: `zone`, `object_type`, `event_id`, `last_detected`, plus
  `license_plate`, `license_plates` and `license_plate_source` on the license
  plate sensors. The plate text as a *state* lives on the per-zone license
  plate sensor described above.

Example automation:

```yaml
automation:
  - alias: Car in the driveway at night
    triggers:
      - trigger: state
        entity_id: binary_sensor.driveway_cam_driveway_vehicle
        to: "on"
    conditions:
      - condition: sun
        after: sunset
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            Vehicle in the driveway
            {{ state_attr('sensor.driveway_cam_detected_object_type', 'license_plates') | join(', ') }}
```

## Known limitation

UniFi Protect's *line-crossing* feature can report a crossing direction
(in/out) in its own web UI, but that direction is **not** modeled anywhere
in the local API data the `uiprotect` client library exposes (checked
against `uiprotect` 15.14.2) - only *which* line was crossed. `lines_crossed`
therefore lists the line(s) touched, but not the direction. If UniFi later
exposes that, `hub.py` is the only place that needs updating.

## Requirements

- Home Assistant 2025.1.0 or newer
- A UniFi Protect NVR reachable on the local network, with a local Protect
  user account
- The `uiprotect` Python package, installed automatically from
  `manifest.json`

## Installation

### Via HACS

This integration is not (yet) part of the HACS default store, so add it as a
custom repository:

1. HACS → the three-dot menu (top right) → **Custom repositories**.
2. Repository: `https://github.com/Internerd/ha-advanced-uprotect`,
   category: **Integration**.
3. Find "UniFi Protect Zone Tracking" in HACS and install it.
4. Restart Home Assistant.

HACS offers the published releases of this repository; see
[CHANGELOG.md](CHANGELOG.md) for what changed between versions.

### Manual / Git

1. Clone this repository, or download and unpack it, and copy the
   `custom_components/unifiprotect_zones` folder into your Home Assistant
   `config/custom_components/` folder:

   ```bash
   git clone https://github.com/Internerd/ha-advanced-uprotect.git
   cp -r ha-advanced-uprotect/custom_components/unifiprotect_zones \
      <path-to-your-ha-config>/custom_components/
   ```

2. Restart Home Assistant.

## Setup

1. Complete one of the installation steps above.
2. Settings → Devices & Services → Add Integration → "UniFi Protect Zone
   Tracking".
3. Enter the same NVR host, a Protect local user (a dedicated read-only
   local account is recommended over reusing the account the core
   integration uses), and whether to verify the NVR's SSL certificate
   (off by default for the typical self-signed local cert).
4. Configure Smart Detection Zones on the cameras you care about inside
   the Protect app itself, if you haven't already - this integration only
   reports on zones that already exist there.
5. Optionally open **Configure** on the integration to change how long the
   per-zone binary sensors stay on.

The config flow, options and entity names are available in English and
German (`custom_components/unifiprotect_zones/translations/`).

## Disclaimer

**No warranty.** This software is provided "as is", without warranty of any
kind, express or implied, including but not limited to the warranties of
merchantability, fitness for a particular purpose and non-infringement. See
the [LICENSE](LICENSE) for the binding text; the summary here is for
convenience only.

**No liability.** In no event shall the authors or copyright holders be
liable for any claim, damages or other liability, whether in an action of
contract, tort or otherwise, arising from, out of or in connection with the
software or the use of or other dealings in the software. You use it at your
own risk.

**Not a safety system.** Detection results come from UniFi Protect's own
smart detection and may be wrong, delayed or missing entirely - a track can
expire before it is fetched, an object can be missed, or a zone can be
mis-assigned. Do not rely on this integration for security-critical,
life-safety or legally relevant purposes.

**Not affiliated with Ubiquiti or Home Assistant.** This is an unofficial
community project. It is not affiliated with, endorsed by, or supported by
Ubiquiti Inc. or the Home Assistant project. "UniFi" and "UniFi Protect" are
trademarks of Ubiquiti Inc., used here only to describe compatibility. Using
this integration may not be covered by, and could conceivably affect, your
support arrangements with Ubiquiti.

**Your responsibility.** Camera footage and detection data are personal data
in many jurisdictions. Operating cameras, recording people and processing
detections is your responsibility, and so is complying with the law that
applies to you. Nothing in this repository is legal advice.

## About this project

- **License**: [MIT](LICENSE) - see the `LICENSE` file for the full text.
  All source code in this repository was written for this project; nothing
  is copied from the Home Assistant core `unifiprotect` integration or any
  other project.
- **Built on**: this integration is a thin Home Assistant wrapper around
  [`uiprotect`](https://github.com/uilibs/uiprotect) ([PyPI](https://pypi.org/project/uiprotect/),
  MIT licensed), the community-maintained Python client for the UniFi
  Protect local API. It does all the actual talking to the NVR; this repo
  only adds zone-path derivation and the Home Assistant entities. It is
  declared as a normal dependency in `manifest.json` and installed
  automatically by Home Assistant - it is not vendored or modified here.
- **AI-assisted development**: This integration was developed with the
  assistance of an AI coding assistant. A human reviewed, tested and takes
  responsibility for the published code. Review it yourself before relying
  on it, especially around authentication and network access. This is
  disclosed for transparency; it is not a substitute for your own code
  review.
- **Security & privacy**: This integration only talks to the local Protect
  NVR you configure - there is no cloud service, telemetry, or third-party
  data transfer involved. Credentials are stored exactly like every other
  Home Assistant integration's config entry (in Home Assistant's local
  `.storage` directory - protect that directory the same way you already
  protect the rest of your Home Assistant config) and are never logged.
  Using a dedicated, read-only local Protect account instead of your admin
  account is recommended (see [Setup](#setup)).
- **Issues / contributions**: Please use the
  [issue tracker](https://github.com/Internerd/ha-advanced-uprotect/issues)
  for bugs and feature requests. Pull requests are welcome.
