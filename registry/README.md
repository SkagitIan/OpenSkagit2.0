# Civic Intelligence Source Registry

A standalone collection of source adapter configurations for the Civic Intelligence Platform. Counties can fork this directory, review existing source examples, and add their own GIS, web, state, or federal data sources without changing agent code.

## How to Use

Copy a source YAML file from `registry/sources/` into `catalog/seeds/`, then reseed the local database:

```bash
python catalog/seeds/seed.py --env local
```

The running platform reads source metadata from the database. This registry is documentation and source configuration only; it is not imported by the application at runtime.

## Structure

```text
sources/
  skagit/
    skagit.yaml
    skagit_web.yaml
  wa_state/
    wa_state.yaml
  federal/
    federal_gis.yaml
    federal_financial.yaml
```

## Contributing

See `CONTRIBUTING.md` for source verification and pull request expectations. See `SCHEMA.md` for the source YAML contract.
