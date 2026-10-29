"""NDW GeoJSON client and response validation."""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import aiohttp
from yarl import URL

from .const import API_URL


class NDWError(Exception):
    """An NDW request or response failed."""


def validate_bbox(value: str) -> str:
    """Normalize and validate an EPSG:4326 bounding box."""
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4 or any(
        re.fullmatch(r"-?\d+(?:\.\d+)?", part, flags=re.ASCII) is None for part in parts
    ):
        raise ValueError("Expected minLon,minLat,maxLon,maxLat")
    west, south, east, north = map(Decimal, parts)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Coordinates must be ordered and within EPSG:4326 bounds")
    normalized = []
    for part in parts:
        number = Decimal(part)
        text = format(number, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        normalized.append("0" if number == 0 else text)
    return ",".join(normalized)


@dataclass(frozen=True)
class Station:
    """One validated charging station."""

    id: str
    address: str
    last_updated: datetime
    total: int | None
    available: int | None
    longitude: float
    latitude: float
    properties: dict[str, Any]


def parse_station(feature: Any) -> Station:
    """Parse required fields; do not turn missing availability into zero."""
    try:
        if not isinstance(feature, dict) or feature["type"] != "Feature":
            raise ValueError("Expected a Feature")
        station_id = feature["id"]
        properties = feature["properties"]
        geometry = feature["geometry"]
        if not isinstance(station_id, str) or not station_id:
            raise ValueError("Missing station ID")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ValueError("Invalid properties or geometry")
        address = properties["address"]
        if not isinstance(address, str) or not address:
            raise ValueError("Invalid address")
        updated = datetime.fromisoformat(
            properties["last_updated"].replace("Z", "+00:00")
        )
        if updated.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        if not isinstance(properties["open"], bool) or not isinstance(
            properties["cpo_id"], str
        ):
            raise ValueError("Invalid open or cpo_id")
        coordinates = geometry["coordinates"]
        if (
            geometry["type"] != "Point"
            or not isinstance(coordinates, list)
            or len(coordinates) != 2
            or any(
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(item)
                for item in coordinates
            )
        ):
            raise ValueError("Invalid point coordinates")
        longitude, latitude = coordinates
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("Point outside EPSG:4326 bounds")
        availabilities = properties.get("availabilities")
        total = available = None
        if availabilities is not None:
            if not isinstance(availabilities, list):
                raise ValueError("Invalid availabilities")
            total = available = 0
            for item in availabilities:
                if not isinstance(item, dict):
                    raise ValueError("Invalid availability")
                count, free = item["total"], item["available"]
                if (
                    type(count) is not int
                    or type(free) is not int
                    or not 0 <= free <= count
                ):
                    raise ValueError("Invalid connection counts")
                total += count
                available += free
        return Station(
            station_id,
            address,
            updated,
            total,
            available,
            longitude,
            latitude,
            properties,
        )
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as err:
        raise NDWError(f"Invalid charging station: {err}") from err


class NDWClient:
    """Fetch complete snapshots, following the API's opaque cursors."""

    def __init__(self, session: aiohttp.ClientSession, bbox: str) -> None:
        self._session = session
        self.bbox = validate_bbox(bbox)

    async def async_get_stations(self) -> dict[str, Station]:
        """Return all pages atomically, failing on malformed pagination."""
        stations: dict[str, Station] = {}
        cursors: set[str] = set()
        params = {"bbox": self.bbox}
        try:
            async with asyncio.timeout(60):
                while True:
                    async with self._session.get(
                        API_URL,
                        params=params,
                        headers={"Accept": "application/geo+json"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        payload = await response.json(content_type=None)
                        next_link = response.links.get("next")
                    if (
                        not isinstance(payload, dict)
                        or payload.get("type") != "FeatureCollection"
                        or not isinstance(payload.get("features"), list)
                    ):
                        raise NDWError("Expected a GeoJSON FeatureCollection")
                    for feature in payload["features"]:
                        station = parse_station(feature)
                        if station.id in stations:
                            raise NDWError(f"Duplicate station ID: {station.id}")
                        stations[station.id] = station
                    if next_link is None:
                        return stations
                    next_url = URL(API_URL).join(URL(str(next_link["url"])))
                    endpoint = URL(API_URL)
                    if (
                        next_url.origin() != endpoint.origin()
                        or next_url.path != endpoint.path
                    ):
                        raise NDWError("Unexpected pagination endpoint")
                    cursor = next_url.query.get("cursor")
                    if not cursor or cursor in cursors:
                        raise NDWError("Missing or repeated pagination cursor")
                    cursors.add(cursor)
                    params = {"bbox": self.bbox, "cursor": cursor}
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise NDWError(f"Unable to fetch NDW charging stations: {err}") from err
