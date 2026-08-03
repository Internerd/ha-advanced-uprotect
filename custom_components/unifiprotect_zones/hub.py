"""Connects to a UniFi Protect NVR and derives zone-path info for smart-detect events.

This talks to the same local Protect API the official ``unifiprotect`` core
integration uses, but pulls a field that integration does not expose: the
ordered sequence of Smart Detection Zones (and crossed lines) a tracked
object moved through during a single event, derived from the per-event
"smart detect track" the NVR keeps only long enough to serve one API call.

Zone *membership* per event is genuinely available from the Protect API.
Line-crossing *direction* (e.g. "in" vs "out") is not modeled by the API at
all as of uiprotect 15.x - only which line id(s) were touched. Anything more
than that would be fabricated, so it is intentionally left out.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from uiprotect import ProtectApiClient
from uiprotect.data import Event, EventType
from uiprotect.data.websocket import WSAction, WSSubscriptionMessage

from .const import SIGNAL_ZONE_EVENT

_LOGGER = logging.getLogger(__name__)

_TRACKED_EVENT_TYPES = {EventType.SMART_DETECT, EventType.SMART_DETECT_LINE}


@dataclass
class ZoneActivity:
    """Zone-path info for one finished smart-detect event."""

    event_id: str
    camera_id: str
    object_type: str | None
    score: int
    zone_path: list[str] = field(default_factory=list)
    lines_crossed: list[str] = field(default_factory=list)

    @property
    def from_zone(self) -> str | None:
        return self.zone_path[0] if self.zone_path else None

    @property
    def to_zone(self) -> str | None:
        return self.zone_path[-1] if self.zone_path else None


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

        event = message.new_obj
        if not isinstance(event, Event):
            return
        if event.type not in _TRACKED_EVENT_TYPES:
            return
        if event.end is None:
            # Event is still in progress; the track is only complete once
            # Protect closes it out, so wait for the update that sets `end`.
            return
        if event.camera_id is None:
            return

        self.hass.async_create_task(self._async_process_event(event))

    async def _async_process_event(self, event: Event) -> None:
        camera = event.camera
        if camera is None:
            _LOGGER.debug("Smart-detect event %s has no resolvable camera", event.id)
            return

        try:
            track = await self.api.get_event_smart_detect_track(event.id)
        except Exception:  # noqa: BLE001 - track can 404 once Protect expires it
            _LOGGER.debug(
                "Could not fetch smart-detect track for event %s", event.id, exc_info=True
            )
            return

        zone_names = {zone.id: zone.name for zone in camera.smart_detect_zones}

        zone_path: list[str] = []
        lines_crossed: list[str] = []
        for item in sorted(track.payload, key=lambda item: item.timestamp):
            frame_zones = tuple(
                sorted(zone_names.get(zid, f"zone-{zid}") for zid in item.zone_ids)
            )
            if frame_zones:
                joined = " + ".join(frame_zones)
                if not zone_path or zone_path[-1] != joined:
                    zone_path.append(joined)

            for line_id in item.lines or []:
                name = zone_names.get(line_id, f"line-{line_id}")
                if name not in lines_crossed:
                    lines_crossed.append(name)

        if not zone_path and not lines_crossed:
            # Nothing zone-related happened (no zones configured on this
            # camera, or the object never entered one) - nothing to report.
            return

        activity = ZoneActivity(
            event_id=event.id,
            camera_id=camera.id,
            object_type=event.smart_detect_types[0].value
            if event.smart_detect_types
            else None,
            score=event.score,
            zone_path=zone_path,
            lines_crossed=lines_crossed,
        )

        async_dispatcher_send(
            self.hass,
            SIGNAL_ZONE_EVENT.format(entry_id=self.entry_id, camera_id=camera.id),
            activity,
        )
