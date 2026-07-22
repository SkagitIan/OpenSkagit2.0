# 2026 Municipal Budget Coverage

Verified on 2026-07-22. This first release covers Skagit County and the county's eight incorporated municipalities. It does not yet cover ports, school districts, fire districts, hospital districts, Skagit Transit, Skagit PUD, library districts, or other special-purpose governments.

| Jurisdiction | Official 2026 source | Source state | Current import state |
| --- | --- | --- | --- |
| Skagit County | [Preliminary budget PDF](https://skagitcounty.net/BudgetFinance/Documents/2026Budget/2026%20Preliminary%20Budget%20%282%29.pdf) | Preliminary; no consolidated adopted book is exposed on the current County page | Reviewed and published in Postgres; PDF archived in private R2 |
| Anacortes | [Final adopted budget](https://www.anacorteswa.gov/DocumentCenter/View/33719/2026-Budget-Book---Final-Adopted) | Adopted | Reviewed and published in Postgres; PDF archived in private R2 |
| Burlington | [Adopted budget](https://burlingtonwa.gov/ArchiveCenter/ViewFile/Item/194) | Adopted; approximately 127 MB | Reviewed and published in Postgres; PDF archived in private R2 |
| Concrete | [Adopted budget book](https://www.townofconcrete.com/wp-content/uploads/2026/01/2026-Budget-Document.pdf) | Adopted; supporting adoption and workshop packets are also cataloged | Reviewed and published in Postgres; PDF archived in private R2 |
| Hamilton | [Official site](https://www.townofhamiltonwa.com/) | No current budget PDF located | Blocked on Town publication or records request |
| La Conner | [Final budget](https://www.townoflaconner.org/DocumentCenter/View/2283/2026-Final-Budget-PDF) | Adopted/final | Reviewed and published in Postgres; PDF archived in private R2 |
| Lyman | [Official site](https://townoflyman.com/) | No current budget PDF located | Blocked on Town publication or records request |
| Mount Vernon | [Adopted budget](https://mountvernonwa.gov/DocumentCenter/View/20136/2026-Budget-Book) | Adopted | Reviewed and published in Postgres; PDF archived in private R2 |
| Sedro-Woolley | [2025-2026 biennial budget book](https://www.sedro-woolley.gov/Departments/Finance/Budget/2025-2026%20Biennial%20Budget%20Book.pdf) | Adopted; later amendments should be separate versions | Reviewed and published in Postgres; PDF archived in private R2 |

Seven primary documents were reviewed and published on 2026-07-22; two Concrete supporting packets remain archival drafts. The release contains 111 reviewed, page-cited rows and 12 top-level totals. Hamilton and Lyman remain source-blocked.

`data/budget_sources.json` is the machine-readable source ledger, `data/budget_reviewed_2026.json` is the reviewed-data ledger, and `data/budget_evals_2026.json` is the known-answer accuracy suite. Raw PDF extraction candidates remain unpublished.
