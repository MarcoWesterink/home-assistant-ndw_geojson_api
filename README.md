# NDW Charging Stations for Home Assistant

Custom integration for the public [NDW GeoJSON charging point API](https://dotnl.ndw.nu/api/rest/geojson/dynamic-road-status/charge-point-data/v1/features).
Configure an area in the UI and get one device per GeoJSON feature.
No API key or YAML configuration is required.

## Install for testing

1. Copy [`custom_components/ndw_geojson_api`](custom_components/ndw_geojson_api)
   into your Home Assistant configuration directory under `custom_components`.
   The resulting path must be `config/custom_components/ndw_geojson_api/manifest.json`.
2. Restart Home Assistant (2025.1 or later).
3. Go to **Settings > Devices & services > Add integration**, then search for
   **NDW Charging Stations**.
4. Enter a bounding box, for example `5.63,52.03,5.65,52.05` for the supplied sample area.
5. Set the polling interval in whole seconds (minimum **60**, default **300**).

The format is **minLon,minLat,maxLon,maxLat**, in EPSG:4326 decimal degrees,
as specified in [`ndw/dafne_api_geojson.yaml`](ndw/dafne_api_geojson.yaml).
Longitude comes first, not latitude. Minimums must be less than maximums.
Use a small area first: every station creates four entities.

## Entities and attributes

Every station has four sensors, enabled by default:

| Sensor | Value |
| --- | --- |
| Address | API `address` |
| Last updated | API `last_updated`, a timezone-aware timestamp |
| Total connections | Sum of `total` across all availability groups |
| Available connections | Sum of `available` across all availability groups |

These are enabled entities visible on the station's device page; the integration
does not automatically add cards to your dashboards.

The **Available connections** sensor also exposes optional details as state
attributes: `station_id`, `latitude`, `longitude`, `open`, `cpo_id`, `country`,
`operator_name`, `owner_name`, `suboperator_name`, and the complete `availabilities`
list (connector format/type, raw maximum power, power type, counts, tariff IDs).
Attributes can be inspected in **Developer tools > States** or used in templates.
Optional fields absent from the API remain absent; explicit nulls are preserved.
The details are attached only to this sensor to avoid four copies in history.

`availabilities: null` or an absent availability list produces **unknown** counts,
not zero. An empty list produces zero counts. The `open` field is preserved as
reported and does not override the availability counts.

**Power units:** the Swagger document describes `power_max` as kW, but the sample
contains values such as `11040.0`. This integration preserves the raw field and
does not convert it or create a power sensor until the units can be confirmed.

## Updates and configuration

- One shared poll per configured area at the configured interval, including all
  pages. The default is **300 seconds** (five minutes), with a minimum of **60 seconds**.
  Existing configurations keep the 300-second default until changed.
- NDW's `Link: ...; rel="next"` pagination passes the opaque cursor unchanged.
- New stations in the area are discovered automatically.
- Stations absent from a successful snapshot become **unavailable**. Their devices
  and entities are retained for stable IDs/history if they return.
- Request failures or malformed responses make sensors unavailable and are reported
  through Home Assistant's coordinator logging. Partial snapshots are not published.
- A valid area containing no stations can still be configured.
- Use the integration's **Configure** option to change the bounding box or polling
  interval in seconds. Saving either setting
  reloads the integration. Old devices outside the area remain in the registry;
  remove them manually if no longer needed.
- Multiple different areas are supported. Overlapping areas create separate
  station devices per integration entry.
- `Last updated` is NDW's timestamp, not the last successful polling time. A
  successful response with an old station timestamp is displayed as received.

## HACS

The repository includes a HACS-compatible layout, [`hacs.json`](hacs.json), and a
versioned integration manifest. It is not automatically listed in HACS.

Once this code is pushed to GitHub, you can test it in HACS:

1. Open HACS, then its menu > **Custom repositories**.
2. Add `https://github.com/MarcoWesterink/home-assistant-ndw_geojson_api`
   with type **Integration**.
3. Download **NDW Charging Stations**, restart Home Assistant, and add the integration.

After testing, create a versioned GitHub release and follow HACS's current
[publication requirements](https://www.hacs.xyz/docs/publish/start/) if you want
inclusion in the default catalog. HACS/Hassfest validation and any required brand
assets should be checked before submitting.

## Development and testing

Client tests can run on Python 3.11+ without Home Assistant:

```shell
pip install -r requirements-dev.txt
pytest -q tests/test_api.py
ruff check .
```

For lifecycle, discovery, failure/recovery, config flow, and options flow tests,
use Linux and a Python version supported by the current Home Assistant test helper:

```shell
pip install -r requirements-ha-test.txt
pytest -q
```

The GitHub Actions workflow uses Python 3.14 and runs both suites. API tests use the
supplied [`sample_response.json`](ndw/sample_response.json) and mocked HTTP; they do
not query NDW. Before relying on the integration, test the actual endpoint and
installation on your Home Assistant instance, especially pagination for larger areas.
