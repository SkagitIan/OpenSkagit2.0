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
      capabilities:
        jurisdiction: "Example City"
        jurisdiction_aliases: ["City of Example"]
        entity_types: ["parcel"]
        query_modes: ["by_parcel", "by_geometry"]
        aggregate_modes: []
        count_supported: false
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

`config.capabilities`: Object. Optional but recommended for planner routing. It describes what the source can answer without exposing endpoint internals to the model.

- `jurisdiction`: Human-readable city, county, state, or agency scope, such as `Sedro-Woolley` or `Skagit County`.
- `jurisdiction_aliases`: Alternate names users may type.
- `entity_types`: Entities accepted by the source, such as `parcel`, `address`, `permit`, `date_range`, or `municipality`.
- `query_modes`: Planner-facing query modes. These should match the source `supports` values without the `query_` prefix.
- `aggregate_modes`: Supported aggregate operations, such as `count_by_status`.
- `count_supported`: Boolean. Set true when the source can support count-style questions.
- `status_fields`: Field names that indicate status for count/filter questions.
- `usage_notes`: Short planner-facing guidance for when to use the source.

## Review Standard

A source is ready when a county IT or GIS reviewer can answer four questions from the YAML alone: which system is queried, who likely owns it, what civic domain it supports, and what kind of identifier the platform sends to it.
