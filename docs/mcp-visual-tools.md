# Property visualization MCP tools

The unified OpenSkagit MCP exposes four read-only tools for producing deterministic, SVG-first editorial assets. They return the normal MCP envelope; the asset metadata is in `data` and includes `asset_id`, `asset_url`, `format`, dimensions, `aspect_ratio`, `source_property_ids`, `fields_used`, warnings, and a human-readable summary.

All tools support `16:9` (1920x1080), `9:16` (1080x1920), `4:5` (1080x1350), and `1:1` (1080x1080). Assets are stored through Django's configured default media storage and can be consumed by a later renderer. The same normalized input and source IDs produce the same asset filename and are reused when present.

`generate_map` accepts `subject_property_id`, `property_ids`, optional `latitude`/`longitude`, `mode`, titles, and highlighted properties. Modes are `subject`, `neighborhood`, `comparables`, `sales`, `land`, `aerial`, and `context`. Property IDs are resolved from active PostGIS/GIS parcel data; missing optional locations become warnings, while an unlocatable subject is an error. The current renderer is a clean editorial schematic map using authoritative parcel coordinates and does not scrape map tiles or aerial imagery.

`generate_property_card` requires `property_id` and accepts `mode` (`subject`, `sale`, `assessment`, `land`, or `improvements`), titles, `highlight_fields`, `requested_fields`, and `aspect_ratio`. It displays only available assessor fields.

`generate_comparison` requires one `subject_property_id` and two-to-three IDs in `comparison_property_ids` (two-to-four total). It accepts requested fields, labels, highlighted fields, titles, and aspect ratio. Unavailable requested fields are omitted with a warning; a missing subject fails the request.

`generate_infographic` requires `infographic_type` and `title`. Types are `big_number`, `bar`, `horizontal_bar`, `range`, `before_after`, `value_breakdown`, `timeline`, and `property_diagram`. Supply exact `values` and matching `labels` where applicable, plus optional units, highlighted items, annotation, property IDs, and source references. Values are formatted, not analytically changed. At most twelve values are accepted; malformed or missing required values return a validation error.

Example calls:

```json
{"subject_property_id":"P45283","property_ids":["P45283","P45284","P45285","P45286"],"mode":"comparables","aspect_ratio":"16:9","title":"A closer look at the neighborhood"}
```

```json
{"property_id":"P45283","mode":"improvements","aspect_ratio":"9:16","highlight_fields":["shop"]}
```

```json
{"subject_property_id":"P45283","comparison_property_ids":["P45284","P45285"],"requested_fields":["sale_price","acres","shop"],"highlight_fields":["shop"]}
```

```json
{"infographic_type":"value_breakdown","title":"What makes up the assessed value?","labels":["Land","House","Outbuildings","Total"],"values":[180000,420000,65000,665000],"units":"USD","aspect_ratio":"9:16"}
```

The response's outer `errors` array follows the standard OpenSkagit contract. Partial data is represented by a successful asset plus `warnings`; no unavailable property fact is guessed.
