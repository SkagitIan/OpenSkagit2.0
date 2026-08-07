# OpenSkagit MCP Compatibility and Deprecation Policy

Status: **approved by Ian on 2026-08-01**  
Draft date: 2026-08-01  
Approved date: 2026-08-01  
Applies to: public stable tools on `https://openskagit.com/mcp/api/`

## Contract authority

The versioned `openskagit_tools` registry and its generated machine-readable
snapshot are the contract authority. MCP discovery, handlers, public/internal
documentation, tests, and operations inventories must be generated from or
validated against that authority.

The Phase 0 stable baseline is the frozen set of 31 version `1.0` read-only tool
names. The 14 target additions are not stable contracts until their admission
gates pass.

## Compatibility classes

A change is backward-compatible only when a conforming existing client can
continue making the same request and interpreting the same successful result
without code or policy changes.

### Compatible changes

- Add a new tool without changing existing tools.
- Add an optional input with a default that preserves existing behavior.
- Add an optional output field without changing existing field types, meaning,
  required presence, ordering promises, or security classification.
- Improve documentation, citations, warnings, or sanitized error detail without
  changing success/failure semantics.
- Fix behavior that was unambiguously outside the documented contract, provided
  active-client impact is reviewed and recorded.

### Breaking changes

- Remove or rename a stable tool.
- Add a required input or make an optional input required.
- Remove, rename, or change the type/meaning of an existing output field.
- Change defaults, units, tax-year selection, jurisdiction coverage, identity
  matching, freshness meaning, pagination, ordering, truncation, or caveats in a
  way that changes an existing client's interpretation.
- Tighten an accepted argument/result limit enough to reject previously valid,
  documented traffic without an emergency security basis and migration plan.
- Change the endpoint, transport, required OAuth scope, or client-authentication
  contract.
- Reclassify public sensitivity or expose additional identity-oriented data.

## Stable breaking-change procedure

1. Record the reason, affected clients/tools, security/privacy impact, and
   replacement in the decision log.
2. Introduce a new versioned tool name or other explicitly versioned contract;
   do not mutate the existing stable contract in place.
3. Publish a migration guide and deprecation date.
4. Run old/new parity tests and representative authenticated client tests.
5. Keep both contracts available for the approved overlap window.
6. Measure use by pseudonymous client/tool metadata without request arguments.
7. Remove the old contract only after known clients migrate or receive an
   approved discontinuation decision and the observation requirement passes.

**Approved overlap:** at least 90 days for a stable public tool, with a longer
window when active-client evidence or owner commitments require it.

## Beta tools

A new public tool starts as beta unless product, domain/methodology,
security/privacy, source-attribution, performance, and operations reviews all
approve stable admission. Beta status permits faster iteration but does not permit
silent removal, sensitive-data exposure, mutation authority, or unbounded
behavior. Document material beta changes and check observed consumers first.

## Additive fields and envelopes

Additive optional fields are compatible only when:

- old fields remain present with their documented type and meaning;
- the new field does not cause a previously public field to become sensitive;
- response-size and deadline budgets still hold;
- clients are not expected to treat unknown fields as errors; and
- snapshots and generated docs are updated together.

A new freshness, provenance, warning, or error field may be additive, but changing
`retrieved_at` into an asserted effective date is semantic and therefore breaking.

## Limits and security emergencies

Limits are part of the public contract. Ordinary limit reductions follow the
breaking-change procedure. When a live contract creates an immediate security,
privacy, legal, source-abuse, or availability threat, operators may fail closed
or temporarily suspend the affected path. They must:

- record the incident and exact reason;
- avoid broad unrelated shutdown;
- notify known clients through the approved support channel;
- provide a safe replacement or remediation plan; and
- obtain product/security direction before permanent breaking removal.

## Deprecation evidence

A stable tool is eligible for retirement only when all apply:

- replacement or intentional discontinuation is approved;
- migration documentation exists;
- known consumers have migrated or have approved discontinuation decisions;
- privacy-safe traffic evidence covers the approved observation window;
- unique data and source dependencies have a disposition;
- protocol, contract, canary, and rollback evidence passes; and
- product, platform, security/privacy, data/methodology, and operations approvals
  are recorded as applicable.

Public reachability, repository search, an expired credential, or zero calls in a
single datastore is not sufficient proof of zero consumers.

## Scope and mutation policy

The current public scope remains `openskagit.read`. A mutation tool, bulk export,
arbitrary SQL, identity-oriented search, sync/rebuild control, administrative
action, or additional OAuth scope is a separately reviewed project and cannot be
introduced as an incidental compatible change.

## Approval record

| Decision | Approved by | Date | Notes |
| --- | --- | --- | --- |
| Policy and 90-day minimum overlap | Ian | 2026-08-01 | Approved; effective immediately |
