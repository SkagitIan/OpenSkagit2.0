# Political Access Risk Checklist

Before deploying the Civic Intelligence Platform for a county, assess each item below. Items marked HIGH risk require a conversation with the relevant department head before go-live. Record the reviewer, date, decision, and any conditions in the county project file.

## GIS Portal Access

- [ ] Who controls access to the county ArcGIS portal?
- [ ] Is the GIS data portal publicly accessible, VPN-only, or behind user authentication?
- [ ] Has the GIS department been informed that the platform will send automated queries?
- [ ] Has GIS approved the expected query volume for launch and normal operations?
- [ ] Is there a rate limit, bot protection rule, or WAF policy that could be triggered?
- [ ] Does the GIS portal expose layers that are public in practice but not intended for broad republishing?
- [ ] Is there a named GIS contact for outage, schema, or layer changes?

HIGH RISK if: GIS department has not been informed, the portal is access-controlled, or the platform would query layers outside the county's approved public data policy.

## Treasurer / Auditor Web Sources

- [ ] Do web adapter queries comply with each site's terms of use?
- [ ] Has the IT department been informed about automated form queries?
- [ ] Has the Treasurer or Auditor reviewed which fields appear in answers and PDFs?
- [ ] Are there CAPTCHA, session, or anti-automation controls that indicate scraping is not welcome?
- [ ] Is there an official API or bulk download that should be used instead of form automation?
- [ ] Are payment, delinquency, foreclosure, or lien fields appropriate for the intended user base?

HIGH RISK if: web scraping is prohibited by site terms, automated access bypasses intended controls, or financial status fields are exposed without department approval.

## Data Sensitivity

- [ ] Does any query surface personally identifiable information (PII)?
- [ ] Is owner name data appropriate for the intended user base?
- [ ] Are there parcels with privacy flags, such as law enforcement, judges, domestic violence survivors, or protected public employees?
- [ ] Are there public records exemptions under state law that affect any source?
- [ ] Could combining multiple public sources reveal sensitive patterns not obvious in a single source?
- [ ] Are minors, health, social services, or criminal justice records excluded?
- [ ] Is there a process for residents or staff to report a sensitive-data concern?

HIGH RISK if: PII is surfaced without appropriate access controls, privacy-suppressed records can be reconstructed, or the source includes protected classes of records.

## Auth and Access

- [ ] Who will receive admin API keys?
- [ ] Who will receive writer API keys for export or sharing workflows?
- [ ] Is the frontend publicly accessible or internal-only?
- [ ] Is Cloudflare Access needed to restrict frontend access?
- [ ] Is the API restricted by network, Cloudflare policy, or key role?
- [ ] Is there a key rotation plan for staff changes and vendor offboarding?
- [ ] Is audit log review assigned to a department or system owner?

HIGH RISK if: the frontend is public and data is sensitive, admin keys are shared by multiple people, or there is no offboarding process.

## Federal Data

- [ ] Is USASpending data appropriate for the intended query types?
- [ ] Are SAM.gov contractor queries within intended use?
- [ ] Are federal source limitations explained to users when confidence is low?
- [ ] Are vendor, grant, or contract answers clearly attributed to federal source names?
- [ ] Does the county need legal review before using federal contractor data in procurement or enforcement workflows?

HIGH RISK if: federal data is used to support decisions beyond the source's intended scope without legal or procurement review.

## Organizational

- [ ] Which department owns this deployment?
- [ ] Which department approves changes to the source catalog?
- [ ] Who approves adding a new source that belongs to another department?
- [ ] Is there a process for removing a source if it is discontinued or disputed?
- [ ] Is there a contact for residents who have questions about the data?
- [ ] Is there a contact for staff who believe an answer is wrong?
- [ ] Is there a launch communication plan for departments whose data appears in answers?
- [ ] Is there a maintenance calendar for dependency, key, and source reviews?

HIGH RISK if: no department owns the deployment, source changes can happen without department approval, or resident/staff escalation paths are undefined.

## Go-Live Signoff

- [ ] GIS owner approved automated access.
- [ ] Treasurer/Auditor owners approved web source use, if enabled.
- [ ] IT approved hosting, access controls, and key management.
- [ ] Legal or records officer reviewed sensitive-data and public-records concerns.
- [ ] Department owner accepted audit log review responsibility.
- [ ] Public-facing wording and contact email are set in `config/tenant.yaml`.
