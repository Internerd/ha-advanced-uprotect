# UniFi Protect Zone Tracking

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

## Installation

### Via HACS

This integration is not (yet) part of the HACS default store, so add it as a
custom repository:

1. HACS → the three-dot menu (top right) → **Custom repositories**.
2. Repository: `https://github.com/Internerd/ha-advanced-uprotect`,
   category: **Integration**.
3. Find "UniFi Protect Zone Tracking" in HACS and install it.
4. Restart Home Assistant.

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
2. Enter the same NVR host, a Protect local user (a dedicated read-only
   local account is recommended over reusing the account the core
   integration uses), and whether to verify the NVR's SSL certificate
   (off by default for the typical self-signed local cert).
3. Configure Smart Detection Zones on the cameras you care about inside
   the Protect app itself, if you haven't already - this integration only
   reports on zones that already exist there.

Requires the `uiprotect` Python package (installed automatically from
`manifest.json`). The config flow and error messages are available in
English and German (`custom_components/unifiprotect_zones/translations/`).

## About this project

- **License**: [MIT](LICENSE) - see the `LICENSE` file for the full text.
- **AI-assisted development**: This integration was developed with the
  assistance of an AI coding assistant (Claude). Review the code yourself
  before relying on it, especially around authentication and network
  access.
- **Disclaimer**: This is an unofficial, community project and is not
  affiliated with, endorsed by, or supported by Ubiquiti Inc. or the Home
  Assistant project. "UniFi" and "UniFi Protect" are trademarks of Ubiquiti
  Inc. Provided "as is", without warranty of any kind - see the
  [LICENSE](LICENSE) for details.
- **Issues / contributions**: Please use the
  [issue tracker](https://github.com/Internerd/ha-advanced-uprotect/issues)
  for bugs and feature requests. Pull requests are welcome.
