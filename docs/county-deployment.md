# County Deployment Overview

This document is for county IT, GIS, records, or administrative staff who need to understand what is being deployed and who controls it.

## What You Receive

You receive the Civic Intelligence Platform repository, deployment instructions, a source registry, and a working web interface. The platform lets authorized users ask questions about public civic records, then returns an answer with evidence, source names, confidence level, and an exportable case file.

## Infrastructure You Control

The county can run the platform in county-owned accounts:

- Railway hosts the Python agent API.
- Cloudflare hosts the frontend and optional adapter Workers.
- SQLite or D1 stores source metadata, jobs, case files, audit logs, and API keys.

The platform does not require the original developer's cloud account after handoff.

## What Data Is Stored

The platform stores operational records only:

- Source metadata.
- Query jobs.
- Case files generated from user questions.
- Audit log entries for each query.
- Hashed API keys.

The platform does not copy or warehouse county GIS, tax, permit, or parcel datasets. It queries approved source systems and records the evidence used in a case file.

## Adding Departments as Sources

Each department source is described by a YAML file. GIS layers, Treasurer searches, Auditor records, and federal datasets can be represented this way if the department approves automated access.

The public source registry in `registry/` includes examples and contribution rules. Start with `registry/CONTRIBUTING.md`, then review the political access checklist before turning on a new source.

## White Labeling

County branding lives in `config/tenant.yaml`. IT can change the county display name, tagline, primary color, contact email, and feature flags without modifying agent code. After changing the file, restart the agent. The `/config` endpoint and frontend will reflect the new values.

## Access Control

API access is protected by API keys. Keys have roles:

- Reader: ask questions and view case files.
- Writer: reader access plus exports.
- Admin: all endpoints, source health, audit log, and key creation.

For public or sensitive deployments, place the frontend behind Cloudflare Access and limit admin keys to named staff.

## When Something Breaks

Use these contacts before launch:

- County system owner: `TBD`
- County IT contact: `TBD`
- GIS contact: `TBD`
- Vendor/developer support: `TBD`

For a source issue, contact the department that owns the source first. For hosting, key, or deployment issues, contact county IT.
