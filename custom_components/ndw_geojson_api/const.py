"""Constants for NDW Charging Stations."""

DOMAIN = "ndw_geojson_api"
CONF_BBOX = "bbox"
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 300
MIN_POLL_INTERVAL = 60
API_URL = (
    "https://dotnl.ndw.nu/api/rest/geojson/"
    "dynamic-road-status/charge-point-data/v1/features"
)
