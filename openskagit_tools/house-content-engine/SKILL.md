---
name: house-content-engine
description: Discover, investigate, verify, script, and produce data-backed homeowner content, with a primary focus on Washington residential property questions. Use when the user wants homeowner video ideas, property-value investigations, assessed-value or tax explainers, remodel/land/neighborhood analysis, a content backlog, scripts based on property evidence, or an end-to-end content package. Prefer original evidence over generic advice, generalize away from individual parcels, and never decide the conclusion before research.
---

# House Content Engine

Use this skill to turn homeowner questions into evidence-backed, production-ready content.

The governing principle is:

**homeowner concern → unanswered question → investigation → verified finding → story → production package**

Prefer **“let's find out”** over **“let me explain.”**

The research result is the product. Storytelling makes it understandable; it does not make it truer.

## Progressive-discovery resources

Read only the resources needed for the requested stage:

- `references/discovery-guide.md` — editorial principles, homeowner concern pillars, question engines, variables, scoring, source hierarchy.
- `references/discovery-workflow.md` — how to generate, feasibility-check, score, rank, and hand off investigations.
- `references/research-verification.md` — population definition, data quality, controls, confounding, fact ledger, evidence grading, research disposition.
- `references/story-development.md` — central reveal, hook, scripts, derivatives, visual beats, narration-ready copy, fact enforcement.
- `references/production-workflow.md` — visual assets, narration, timing, manifests, rendering, QA, and distribution package.
- `references/state-contracts.md` — canonical stage states and handoff objects.

For a full autonomous episode, read all six.

## Default audience and geography

Default audience: homeowners and people making residential-property decisions.

Default editorial market: Washington State.

Use local/county property data as an analytical laboratory where appropriate. Never imply that a finding from one county automatically applies statewide.

Specific parcels may be used internally to trigger or test an idea, but public-facing content should normally generalize to a homeowner question. Avoid unnecessary parcel IDs, exact addresses, owner names, or personally identifying details.

## Capability discovery

Do not hardcode one property-data server, county, or toolset.

Before proposing a data-driven investigation, inspect the tools available in the current environment and build an internal capability map. Look for capabilities such as:

- parcel/property lookup
- sales and sale validation
- assessed-value history
- land and improvement detail
- neighborhood/geographic identifiers
- permits/remodel indicators
- property characteristics
- tax/levy information
- zoning, utilities, waterfront, view, access, or development constraints
- mapping and visualization
- narration generation
- video rendering

Use the strongest available tools. If a requested question requires unavailable or unreliable data, downgrade or reject it rather than pretending it can be answered.

If production tools such as map, property-card, comparison, infographic, narration, or video generators are available, use them according to their contracts. Do not require those exact names if equivalent capabilities exist.

## Source discipline

Use web/community sources to discover what homeowners are asking.

Use authoritative sources for rules and factual legal/administrative context. For Washington questions, prefer current official sources in roughly this order:

1. Washington Legislature
2. Washington Department of Revenue
3. Washington Board of Tax Appeals
4. Washington Department of Commerce when relevant
5. county assessors, Boards of Equalization, planning/zoning, GIS, permit systems, and other local government sources
6. structured property/market evidence

Community discussion can identify confusion and demand. It does not prove the rule or the market conclusion.

For current laws, rules, market conditions, policy changes, or current homeowner concerns, verify with fresh web research rather than relying on stored examples.

## Modes

Infer the narrowest mode that satisfies the user.

### Discovery mode

Use when the user asks for ideas, topics, a backlog, or “what should we investigate?”

Read the Discovery Guide and Discovery Workflow.

Return researchable questions, not predetermined titles or conclusions.

### Research mode

Use when the user supplies or selects an investigation and wants to know what the evidence shows.

Read Research & Verification.

End with one disposition:

- `ADVANCE`
- `ADVANCE_WITH_LIMITATIONS`
- `REFRAME`
- `RETURN_TO_DISCOVERY`

### Story mode

Use when research is already verified and the user wants the story, script, hooks, derivatives, or visual plan.

Read Story Development.

Never add a factual statement that cannot map to the fact ledger.

### Production mode

Use when approved scripts/evidence already exist and the user wants finished media or a production package.

Read Production Workflow.

The renderer executes editorial decisions; it does not make them.

### Full autonomous mode

Use when the user asks the skill to choose and produce the next episode or otherwise run end-to-end.

Execute:

1. DISCOVER
2. FEASIBILITY CHECK
3. SELECT
4. RESEARCH
5. VERIFY
6. STORY
7. FACT QA
8. GENERATE ASSETS
9. GENERATE NARRATION
10. ALIGN TIMING
11. BUILD MANIFESTS
12. RENDER
13. AUDIOVISUAL + FACT QA
14. PACKAGE

If research fails, return to Discovery and choose another strong candidate. Do not force a failed investigation into production.

## Discovery rule

A strong idea contains an unanswered question that available evidence can plausibly resolve.

Prefer questions involving:

- a surprising relationship
- two variables people assume move together
- same-X/different-Y comparisons
- marginal contribution or diminishing returns
- neighborhood/boundary effects
- before/after patterns
- outliers
- expected-versus-observed outcomes

Weak: `How does property tax work?`

Strong: `How can assessed value fall while a homeowner's property-tax bill rises?`

Weak: `Does acreage affect value?`

Strong: `Does the second acre appear to contribute as much as the first among otherwise similar residential sales?`

Do not write the reveal before the evidence exists.

## Research rule

Define the population and major filters before interpreting results.

Know the analytical unit. Prevent duplicated parcels/sales caused by joins to land segments, improvements, permits, or other one-to-many tables.

Start simple, then test obvious confounders.

Residential confounders commonly include:

- location/neighborhood
- living area
- acreage
- age and effective age
- condition and quality
- waterfront/view
- garage/shop/outbuildings
- utilities/zoning/access
- sale date and market cycle

Prefer association language unless causal evidence genuinely exists.

A negative or surprising result may be stronger than the original hypothesis.

## Fact ledger gate

Before Story, create a fact ledger. Every substantive production claim must be one of:

- `VERIFIED_FACT`
- `CALCULATED_RESULT`
- `ANALYSIS_INTERPRETATION`

Each important fact should retain source/provenance, population or property references, calculation where applicable, confidence, limitations, and whether it is approved for public use.

If a script statement cannot map to an approved ledger entry, verify it or delete it.

Downstream graphics, narration, and video tools must never independently decide factual values.

## Evidence gate

Rate evidence:

- `A` — strong
- `B` — good with limitations
- `C` — exploratory
- `D` — insufficient

Also rate storyworthiness separately.

Do not advance a technically valid but uninteresting investigation solely because research time has already been spent.

## Story rule

Find one central reveal.

Default narrative arc:

**HOOK → SETUP → EVIDENCE → REVEAL → EXPLANATION → PRACTICAL MEANING → CLOSE**

The homeowner should experience:

**“I thought I knew the answer.” → “That's interesting.” → “Now I understand why.”**

Keep methodology sufficient for credibility but subordinate to the finding.

Write for speech, not reports. Use clear sentences, natural number phrasing, and minimal appraisal jargon.

## Platform strategy

Develop one evidence-backed master story first, then derive native pieces.

Do not mechanically crop a YouTube video into every platform.

Potential outputs include:

- 4–8 minute 16:9 explainer when evidence warrants depth
- 45–90 second 9:16 short
- additional 9:16 shorts only when they contain genuinely different reveals
- static graphic or carousel when the result is especially visual
- platform-ready title/caption/description variants

When practical, a strong vertical version may exceed 60 seconds, but editorial quality comes first.

## Visual rule

Prefer **showing the evidence while explaining it** over generic illustrative footage.

Use maps, comparisons, property cards, charts, and infographics when they communicate the finding.

Data-bearing visuals must use approved fact-ledger values and suitable aspect-specific layouts. Do not blindly crop landscape data graphics into vertical formats.

## Vertical video composition contract

For every 9:16 production, treat 1080x1920 as the actual design canvas. Use exactly one scene grammar per scene:

- `DATA_FULL_FRAME` — one purpose-built data visual fills the frame.
- `MEDIA_FULL_FRAME` — one photograph or contextual media asset fills the frame.
- `MEDIA_WITH_DATA_CARD` — full-bleed media plus one compact data card.
- `SPLIT_COMPARE` — one purpose-built comparison composition, not stacked posters.

Scenes replace one another sequentially. They do not accumulate full-size assets. A data scene may not use background stock footage or a placeholder carrier. Never use `samples/elephants`, arbitrary stock, or black filler to satisfy a renderer requirement.

For data visuals, request `presentation_mode="video_scene"`. Keep the visual glance-readable: one main idea, one major number or relationship, and minimal supporting text. Captions are phrase-level overlays in the dedicated bottom safe zone; they must not cross the primary visual or repeat a data callout unnecessarily. Use abbreviated display values such as `$195,100`, while narration may retain natural spoken phrasing.

Use the neutral series identity `HOME VALUE BRIEF` for generalized public visuals. Apply the shared navy, off-white, teal, coral, and gold palette, the H-mark, the headline rule, and the footer lockup consistently. Do not expose the internal OpenSkagit name in generalized public-facing artwork.

### Short-form design principles

Treat hierarchy, legibility, and timing as functional requirements. Make the question or hook the largest readable element, keep one primary idea per scene, and use motion to direct attention rather than decorate. Use high-contrast caption containers, phrase-level grouping, and a dedicated safe zone; captions must not obscure relevant data. Keep essential text away from platform UI edges and test at the intended phone-sized viewing scale. These practices align with WCAG contrast/readability guidance and platform safe-zone behavior.

## Narration and timing

Only generate narration after factual and narrative QA.

Do not ask narration tools to rewrite approved text.

Preserve the original script and any provider-normalized/aligned transcript separately.

Use actual narration timing for captions, overlays, and scene transitions when timing metadata is available. Do not estimate timing when real alignment exists.

### Cue-driven synchronization

Every approved synchronized script should define `script_cues`. Each cue has a stable `cue_id`, exact approved `text`, and optional `fact_ids`. Visual beats reference one or more cue IDs through `cue_id` or `cue_ids`.

After narration, the engine matches each cue to ElevenLabs `word_timings`. It derives scene onset from the matched words, holds the active visual through pauses, and ends it at the next visual cue or narration end. The production manifest receives those derived `start` and `duration` values as a renderer-neutral timeline. An unmatched cue, missing visual cue, or non-contiguous timing is a production error, not a reason to guess.

## Production rule

Production consumes the approved story package.

The production layer may decide technical rendering details, but it must not decide:

- facts
- conclusions
- which statistical interpretation is correct
- new claims
- new property examples

Create deterministic manifests and preserve source asset IDs, narration asset IDs, fact/evidence references, and output provenance where the available tools support it.

For the default video path, expose one creation action but preserve two internal retry boundaries:

1. prepare an immutable bundle containing the approved manifest, exact narration, downloaded scene assets, captions, and resolved timing
2. render the bundle into a real MP4, run technical QA, upload the verified master, and write its durable episode catalog record

Do not create or request a base video, carrier, or filler asset. The timeline and scene durations define the finished video. Prefer deterministic local composition for still/data-led episodes; use Cloudinary for final storage, delivery, thumbnails, and derivatives. A provider transformation may be used only when it is genuinely the simpler verified renderer for the episode type.

A house-content video is not complete until the final media asset is durable and its `ready` catalog record makes it visible in `/staff/house-content/`. If catalog persistence fails, report production failure rather than returning a nominally successful video URL.

## QA gates

Before rendering:

- all factual script lines map to the ledger
- data-bearing visuals match the ledger
- public-use/privacy flags are honored
- required assets exist
- aspect-specific layouts are readable

After rendering:

- media loads and plays
- narration is complete
- captions align
- overlays appear at intended spoken moments
- no important visual information is cropped
- every visible/spoken number matches the ledger
- no stale/wrong parcel asset appears
- final duration and dimensions are sensible

A provider success response is not sufficient when the finished asset can be inspected.

## Distribution boundary

This skill may create a distribution-ready package, including media assets, titles, captions, descriptions, thumbnails, source notes, and a distribution manifest.

Do not publish automatically unless the user explicitly requests publishing and an appropriate connected publishing capability is available.

Prefer human approval initially.

## Analytics boundary

Performance analytics are intentionally separate from this skill.

Do not turn this skill into an ongoing analytics engine.

A future performance skill may feed learned recommendations back into Discovery, but production should function independently.

## Autonomous decision policy

Do not ask the user to choose between equivalent candidates when the skill can make a defensible editorial decision.

Ask only when user preference materially changes the outcome or required information cannot be resolved with available evidence/tools.

For full autonomous mode, make the selection and continue.

## Failure handling

Do not manufacture a result.

If evidence fails:

- preserve the failed investigation and reason
- reframe if a stronger nearby question emerged
- otherwise return to Discovery

If production tooling fails:

- distinguish editorial/data failure from provider/render failure
- repair within the current production contract where possible
- do not silently alter facts or script to make rendering easier

## Final package

For a completed investigation, preserve conceptually:

- story/investigation ID
- original homeowner question
- research scope and population
- fact ledger
- evidence grade and limitations
- central reveal
- approved scripts
- source package
- visual assets and provenance
- narration asset and timing
- production manifests
- rendered media outputs
- social/package metadata
- QA status

Use `references/state-contracts.md` for canonical handoff fields.

## Core quality test

Before calling the work complete, verify:

1. Would a homeowner immediately understand why the question matters?
2. Was the answer genuinely investigated rather than assumed?
3. Could another variable reasonably explain the relationship, and was that considered?
4. Can every important claim be traced to evidence?
5. Is the public story broader than one identifiable parcel?
6. Does the content reveal something rather than merely define something?
7. Do the visuals prove or clarify the point?
8. Would the story remain interesting if the original hypothesis was wrong?

If not, improve the investigation or choose another one.
