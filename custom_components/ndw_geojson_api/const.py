"""Constants for NDW Charging Stations."""

from datetime import timedelta

DOMAIN = "ndw_geojson_api"
CONF_BBOX = "bbox"
UPDATE_INTERVAL = timedelta(minutes=5)
API_URL = (
    "https://dotnl.ndw.nu/api/rest/geojson/"
    "dynamic-road-status/charge-point-data/v1/features"
)
