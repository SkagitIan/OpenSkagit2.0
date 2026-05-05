# Source YAML Schema

Source YAML files use this shape:

```yaml
sources:
  source_id:
    name: "Human-readable name"
    type: "arcgis"
    base_url: "https://example.gov/arcgis/rest/services/Parcels/FeatureServer"
    domains: ["parcels"]
    supports: ["by_parcel", "by_geometry"]
    config:
      layer: 0
      parcel_field: "PARCELID"
```

## Fields

`sources`: Object. Required. Keys are source IDs. Values are source definitions.

`id`: String. Required as the object key. Use lowercase letters, numbers, and underscores. IDs must be stable because audit logs and case files refer to them.

`name`: String. Required. The display name used in evidence, PDFs, and admin screens.

`type`: String. Required. Allowed values:

- `arcgis`: ArcGIS REST services queried through the ArcGIS adapter.
- `web`: Public web systems queried through the web adapter.
- `federal`: Federal APIs or public federal datasets.

`base_url`: String. Required. The public root URL or service URL. Do not include API keys, session cookies, or user-specific tokens.

`domains`: Array of strings. Required. Domains describe what civic questions the source can answer. Common values include `parcels`, `zoning`, `permits`, `taxes`, `wetlands`, `critical_areas`, `water_rights`, `federal_land`, `contractors`, and `spending`.

`supports`: Array of strings. Required. Query modes the adapter can execute. Common values include:

- `by_parcel`: Query by parcel identifier.
- `by_geometry`: Query by shape or location.
- `by_address`: Query by address text.
- `by_name`: Query by person, vendor, contractor, or agency name.
- `by_record_id`: Query by permit, invoice, contract, or document ID.

`config`: Object. Required, but may be empty when the adapter needs no extra settings. Adapter-specific examples:

```yaml
config:
  layer: 0
  parcel_field: "PARCELID"
  out_fields: ["PARCELID", "OwnerName", "Acres"]
  spatial_reference: 2927
```

```yaml
config:
  search_path: "/Search"
  method: "GET"
  result_selector: "table.results"
```

## Review Standard

A source is ready when a county IT or GIS reviewer can answer four questions from the YAML alone: which system is queried, who likely owns it, what civic domain it supports, and what kind of identifier the platform sends to it.
