# Contributing Sources

Source YAML files describe data systems the Civic Intelligence Platform can query through an adapter. A county should be able to read a source file and understand who owns the data, what it supports, and which adapter is used.

## Required Fields

Every source entry must include:

- `id`: Stable lowercase identifier. Use a county or agency prefix, for example `skagit_parcels`.
- `name`: Human-readable source name shown in evidence and admin screens.
- `type`: Adapter family. Use `arcgis`, `web`, or `federal`.
- `base_url`: Root service URL or endpoint used by the adapter.
- `domains`: Query domains this source answers, such as `parcels`, `zoning`, `wetlands`, `taxes`, or `spending`.
- `supports`: Query methods the source supports, such as `by_parcel`, `by_geometry`, or `by_name`.
- `config`: Adapter-specific settings. For ArcGIS this usually includes layer IDs, parcel fields, or spatial reference settings.
- `config.capabilities`: Planner-facing metadata for scalable routing. Include jurisdiction, aliases, entity types, query modes, aggregate modes, count support, status fields, and concise usage notes when the source answers jurisdiction-specific questions such as permits.

Use `catalog/seeds/skagit.yaml` as the reference style for ArcGIS sources and `catalog/seeds/skagit_web.yaml` as the reference style for web sources.

For a new city permit source, add a `permits` source with a city `jurisdiction`, aliases users may type, query modes such as `by_date`, `by_address`, and `by_permit`, and `count_supported: true` only if citywide count questions can be answered reliably.

## Verification Before Submitting

1. Confirm the source owner and public access status.
2. Confirm the URL is reachable from a network outside the county firewall, unless the deployment is internal-only.
3. Confirm the spatial reference and geometry behavior for GIS sources.
4. Confirm at least one known query works against a real parcel, address, permit number, contractor, or other entity.
5. Run source verification:

```bash
python catalog/tools/verify_sources.py
```

If the source requires county-only credentials or VPN access, document that in the pull request and do not include secrets in YAML.

## Pull Request Checklist

- [ ] Source is reachable from the intended deployment network.
- [ ] Source owner or department is identified in the source name or description.
- [ ] Spatial reference is confirmed for GIS sources.
- [ ] At least one `domain` is listed.
- [ ] At least one `supports` query mode is listed.
- [ ] No API keys, passwords, cookies, or private tokens are committed.
- [ ] Automated query use has been reviewed with the department that owns the system.
- [ ] The source does not expose restricted PII to users who should not see it.
