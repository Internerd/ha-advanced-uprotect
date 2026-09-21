"""Connects to a UniFi Protect NVR and derives zone-path info for smart-detect events.

This talks to the same local Protect API the official ``unifiprotect`` core
integration uses, but pulls a field that integration does not expose: the
ordered sequence of Smart Detection Zones (and crossed lines) a tracked
object moved through during a single event, derived from the per-event
"smart detect track" the NVR keeps only long enough to serve one API call.

Zone *membership* per event is genuinely available from the Protect API, and
so is the object type of every single track point - and, for vehicles, the
recognized license plate. That is what lets this integration say *which*
object, and *which* plate, was in *which* zone. Line-crossing
*direction* (e.g. "in" vs "out") is not modeled by the API at all as of
uiprotect 15.x - only which line id(s) were touched. Anything more than that
would be fabricated, so it is intentionally left out.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from uiprotect import ProtectApiClient
from uiprotect.data import Camera, Event, EventType
from uiprotect.data.devices import SmartMotionZone
from uiprotect.data.nvr import SmartDetectTrack
from uiprotect.data.websocket import WSAction, WSSubscriptionMessage
from uiprotect.exceptions import UnifiProtectError

from .const import (
    OBJECT_TYPE_LICENSE_PLATE,
    OBJECT_TYPE_VEHICLE,
    PLATE_CARRIER_TYPES,
    PLATE_SOURCE_EVENT,
    PLATE_SOURCE_ZONE,
    SIGNAL_ZONE_EVENT,
    SIGNAL_ZONES_UPDATED,
    ZONE_OBJECT_TYPES,
    normalize_object_type,
)

_LOGGER = logging.getLogger(__name__)

_TRACKED_EVENT_TYPES = {EventType.SMART_DETECT, EventType.SMART_DETECT_LINE}

type ProtectZonesConfigEntry = ConfigEntry[ProtectZoneHub]


@dataclass
class ZoneDetection:
    """What a single event saw inside one Smart Detection Zone."""

    zone_id: int
    zone_name: str
    object_types: set[str] = field(default_factory=set)
    license_plates: list[str] = field(default_factory=list)
    license_plate_source: str | None = None

    @property
    def license_plate(self) -> str | None:
        """The most recent plate read for this zone during the event."""
        return self.license_plates[-1] if self.license_plates else None

    @property
    def object_type_list(self) -> list[str]:
        """Object types seen in this zone, in a stable order."""
        return sorted(self.object_types)


@dataclass
class ZoneActivity:
    """Zone-path info for one finished smart-detect event."""

    event_id: str
    camera_id: str
    object_type: str | None
    score: int
    object_types: list[str] = field(default_factory=list)
    zone_path: list[str] = field(default_factory=list)
    zones: list[str] = field(default_factory=list)
    lines_crossed: list[str] = field(default_factory=list)
    license_plates: list[str] = field(default_factory=list)
    detections_by_zone: dict[int, ZoneDetection] = field(default_factory=dict)

    @property
    def license_plate(self) -> str | None:
        """The most recent plate read anywhere in this event."""
        return self.license_plates[-1] if self.license_plates else None

    @property
    def from_zone(self) -> str | None:
        return self.zone_path[0] if self.zone_path else None

    @property
    def to_zone(self) -> str | None:
        return self.zone_path[-1] if self.zone_path else None


def camera_reports_zones(camera: Camera) -> bool:
    """Whether this camera can produce zone activity at all.

    A camera only gets entities once it has a Smart Detection Zone or can
    cross lines. Both can appear after setup - drawing the *first* zone in
    the Protect app is what turns a camera into one this integration has
    anything to say about - so the platforms re-check this whenever zones
    change, not just at startup.
    """
    return bool(
        camera.smart_detect_zones
        or getattr(camera.feature_flags, "has_line_crossing", False)
    )


def zone_object_types(zone: SmartMotionZone) -> list[str]:
    """Return the object types worth creating an entity for in this zone.

    Protect stores which object types a zone actually detects. Honouring that
    keeps the entity list to what the camera can really report; a zone with no
    explicit configuration gets the full set.
    """
    configured = {
        normalize_object_type(object_type.value)
        for object_type in zone.object_types or []
    }
    if not configured:
        return list(ZONE_OBJECT_TYPES)

    types = [
        object_type for object_type in ZONE_OBJECT_TYPES if object_type in configured
    ]
    # Plates are only ever read off vehicles, and Protect does not list them
    # as a separate zone object type.
    if OBJECT_TYPE_VEHICLE in configured and OBJECT_TYPE_LICENSE_PLATE not in types:
        types.append(OBJECT_TYPE_LICENSE_PLATE)
    return types


def event_license_plates(event: Event) -> list[str]:
    """Plates Protect attached to the event itself.

    Depending on firmware the plate text shows up on the vehicle track point,
    on a separate ``licensePlate`` detection thumbnail for the same event, or
    on both. Reading the event metadata as well means the plate is not lost
    when only the second form is populated.
    """
    plates: list[str] = []
    metadata = getattr(event, "metadata", None)
    for thumbnail in getattr(metadata, "detected_thumbnails", None) or []:
        if normalize_object_type(thumbnail.type or "") != OBJECT_TYPE_LICENSE_PLATE:
            continue
        plate = (thumbnail.name or "").strip()
        if plate and plate not in plates:
            plates.append(plate)
    return plates


def build_zone_activity(
    event: Event, camera: Camera, track: SmartDetectTrack
) -> ZoneActivity | None:
    """Turn one event's smart-detect track into a :class:`ZoneActivity`.

    Returns ``None`` when the track never touched a zone or a crossing line,
    which is everything this integration has nothing to say about.
    """
    zone_names = {zone.id: zone.name for zone in camera.smart_detect_zones}

    zone_path: list[str] = []
    zones: list[str] = []
    lines_crossed: list[str] = []
    license_plates: list[str] = []
    object_types: list[str] = []
    detections: dict[int, ZoneDetection] = {}

    for item in sorted(track.payload, key=lambda item: item.timestamp):
        item_type = normalize_object_type(item.object_type.value)
        if item_type not in object_types:
            object_types.append(item_type)

        plate = (item.license_plate or "").strip()
        if plate and plate not in license_plates:
            license_plates.append(plate)

        frame_zones = tuple(
            sorted(zone_names.get(zid, f"zone-{zid}") for zid in item.zone_ids)
        )
        if frame_zones:
            joined = " + ".join(frame_zones)
            if not zone_path or zone_path[-1] != joined:
                zone_path.append(joined)
            for name in frame_zones:
                if name not in zones:
                    zones.append(name)

        for zone_id in item.zone_ids:
            detection = detections.get(zone_id)
            if detection is None:
                detection = detections[zone_id] = ZoneDetection(
                    zone_id=zone_id,
                    zone_name=zone_names.get(zone_id, f"zone-{zone_id}"),
                )
            detection.object_types.add(item_type)
            if plate:
                # A plate read implies a vehicle carrying it, and it is what
                # the per-zone "license plate" entities report on.
                detection.object_types.add(OBJECT_TYPE_LICENSE_PLATE)
                detection.license_plate_source = PLATE_SOURCE_ZONE
                if plate not in detection.license_plates:
                    detection.license_plates.append(plate)

        for line_id in item.lines or []:
            # Protect does not expose crossing-line names anywhere in the
            # local API, so the id is all there is to report.
            name = f"line-{line_id}"
            if name not in lines_crossed:
                lines_crossed.append(name)

    for plate in event_license_plates(event):
        if plate not in license_plates:
            license_plates.append(plate)

    if len(license_plates) == 1:
        # Protect regularly reads the plate on a frame that carries no zone
        # ids, or reports it only on the event. With exactly one plate in the
        # whole event there is no ambiguity about which vehicle it belongs to,
        # so every zone that saw a vehicle saw that plate. More than one plate
        # would mean guessing, and that is left alone.
        plate = license_plates[0]
        for detection in detections.values():
            if detection.license_plates:
                continue
            if not detection.object_types & PLATE_CARRIER_TYPES:
                continue
            detection.license_plates.append(plate)
            detection.object_types.add(OBJECT_TYPE_LICENSE_PLATE)
            detection.license_plate_source = PLATE_SOURCE_EVENT

    for smart_type in event.smart_detect_types:
        normalized = normalize_object_type(smart_type.value)
        if normalized not in object_types:
            object_types.append(normalized)

    if not zone_path and not lines_crossed:
        # Nothing zone-related happened (no zones configured on this camera,
        # or the object never entered one) - nothing to report.
        return None

    return ZoneActivity(
        event_id=event.id,
        camera_id=camera.id,
        object_type=object_types[0] if object_types else None,
        object_types=object_types,
        score=event.score,
        zone_path=zone_path,
        zones=zones,
        lines_crossed=lines_crossed,
        license_plates=license_plates,
        detections_by_zone=detections,
    )


class ProtectZoneHub:
    """Owns the Protect API connection for one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        host: str,
        port: int,
        username: str,
        password: str,
        verify_ssl: bool,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.api = ProtectApiClient(
            host=host,
            port=port,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
            session=async_create_clientsession(hass, verify_ssl=verify_ssl),
            subscribed_models=None,
        )
        self._unsub_ws: Callable[[], None] | None = None

    @property
    def cameras(self) -> list[Camera]:
        """Every camera this integration can report zone activity for."""
        return [
            camera
            for camera in self.api.bootstrap.cameras.values()
            if camera_reports_zones(camera)
        ]

    def get_camera(self, camera_id: str) -> Camera | None:
        """Look up a camera in the current bootstrap."""
        return self.api.bootstrap.cameras.get(camera_id)

    async def async_connect(self) -> None:
        """Log in, load the bootstrap and start the realtime websocket."""
        await self.api.update()
        self._unsub_ws = self.api.subscribe_websocket(self._handle_ws_message)

    async def async_disconnect(self) -> None:
        if self._unsub_ws is not None:
            self._unsub_ws()
            self._unsub_ws = None
        await self.api.async_disconnect_ws()
        await self.api.close_session()

    def _handle_ws_message(self, message: WSSubscriptionMessage) -> None:
        """Filter the realtime feed down to finished smart-detect events."""
        if message.action not in (WSAction.ADD, WSAction.UPDATE):
            return

        new_obj = message.new_obj

        if isinstance(new_obj, Camera):
            # Zones added in the Protect app show up as a camera update; tell
            # the platforms so they can create the matching entities.
            if "smart_detect_zones" in (message.changed_data or {}):
                self._async_notify_zones_updated(new_obj.id)
            return

        if not isinstance(new_obj, Event):
            return
        if new_obj.type not in _TRACKED_EVENT_TYPES:
            return
        if new_obj.end is None:
            # Event is still in progress; the track is only complete once
            # Protect closes it out, so wait for the update that sets `end`.
            return
        if new_obj.camera_id is None:
            return

        self.hass.async_create_task(self._async_process_event(new_obj))

    @callback
    def _async_notify_zones_updated(self, camera_id: str) -> None:
        async_dispatcher_send(
            self.hass,
            SIGNAL_ZONES_UPDATED.format(entry_id=self.entry_id),
            camera_id,
        )

    async def _async_process_event(self, event: Event) -> None:
        camera = event.camera
        if camera is None:
            _LOGGER.debug("Smart-detect event %s has no resolvable camera", event.id)
            return

        try:
            track = await self.api.get_event_smart_detect_track(event.id)
        except (UnifiProtectError, aiohttp.ClientError, TimeoutError):
            # The track 404s once Protect has expired it, and a network hiccup
            # on a single event must not bubble out of this task.
            _LOGGER.debug(
                "Could not fetch smart-detect track for event %s",
                event.id,
                exc_info=True,
            )
            return

        activity = build_zone_activity(event, camera, track)
        if activity is None:
            return

        # New zones may have been configured since the last event.
        self._async_notify_zones_updated(camera.id)

        async_dispatcher_send(
            self.hass,
            SIGNAL_ZONE_EVENT.format(entry_id=self.entry_id, camera_id=camera.id),
            activity,
        )
