# Production Workflow

## Goal

Turn an approved Story handoff into finished, inspectable media while preserving factual integrity and provenance.

Production does not research, reinterpret evidence, or invent claims.

## 1. Production input gate

Require `READY_FOR_PRODUCTION` or `READY_WITH_LIMITATIONS` plus:

- approved scripts
- fact ledger reference
- script fact map
- visual beats
- approved overlay text
- source package
- prohibited claims
- target formats

If any required factual value is unresolved, return to Research/Story rather than guessing.

## 2. Discover media capabilities

Inspect available tools for:

- maps
- property cards
- comparison graphics
- infographics/charts
- narration/TTS with timing
- media storage
- video rendering

Use existing production services rather than rebuilding equivalent functionality.

## 3. Generate visual assets

Create only visuals required by the storyboard.

For data-bearing graphics:

- pass approved values explicitly
- preserve source/evidence IDs
- use aspect-specific layouts
- avoid destructive cross-aspect cropping
- remove unnecessary parcel IDs/addresses/owner information
- request `presentation_mode="video_scene"` for video assets; reserve dense standalone layouts for static/social output
- design vertical graphics on a real 1080x1920 canvas rather than shrinking a landscape poster

Inspect generated visuals when possible. A successful API response does not guarantee a readable graphic.

## 4. Narration

Generate narration from the approved script exactly. Preserve:

- original script
- provider-normalized/aligned transcript
- audio asset
- voice/model/settings metadata
- duration
- character/word/segment timing where available

Do not perform speech recognition when provider alignment already exists.

## 5. Captions

Build captions from real narration timing. Prefer readable phrase/sentence grouping rather than one-word karaoke captions unless the product specifically calls for it.

Keep captions inside safe areas for each target format.

For 9:16, use the shared composition contract: captions belong approximately in y=1460–1710, with a bottom platform-safe margin. Keep them to no more than two lines and phrase-level groups. A scene has one primary visual; only explicitly declared compact callouts may accompany it. Never add unrelated stock footage as a base video.

## 6. Timing refinement

Use actual narration timing to place:

- scene changes
- number overlays
- chart/graphic reveals
- emphasis labels

Never estimate timing when alignment provides it.

For synchronized episodes, define exact `script_cues` with stable IDs and reference those IDs from visual beats. Use ElevenLabs `word_timings` as the timing authority. Derive visual onsets from the matched words, hold visuals through pauses, and place the resulting contiguous `start` and `duration` values in the renderer-neutral manifest. Do not divide narration duration evenly across scenes.

## 7. Production manifest

Create a machine-readable manifest that describes editorial intent, not renderer syntax.

Each scene should include conceptually:

- scene ID
- duration or computed start/end
- asset reference
- motion preset if useful
- transition
- timed overlays
- evidence/fact references
- `scene_type`: `DATA_FULL_FRAME`, `MEDIA_FULL_FRAME`, `MEDIA_WITH_DATA_CARD`, or `SPLIT_COMPARE`
- one `primary_asset`; do not stack independent complete graphics

Top level should include target aspect/dimensions, narration asset, captions, and render version/metadata.

Preserve both the durable asset ID and a resolvable delivery URL or local path for every render input. This lets preparation freeze exact inputs without repeated provider metadata lookups.

## 8. Motion/transitions

Use a restrained vocabulary such as:

- none
- slow zoom in/out
- slow pan
- cut
- crossfade

Data readability beats motion. Do not animate every scene. The deterministic default renderer may intentionally accept only `none` and `cut`; reject unsupported effects during manifest validation instead of approximating them silently.

## 9. Render

For still- and data-led episodes, use the carrier-free two-stage path:

1. **Prepare** — freeze narration, scene inputs, captions, and resolved timing into an immutable bundle.
2. **Render and publish** — compose a real MP4 with FFmpeg, inspect it locally, upload the verified master to Cloudinary, and persist the episode catalog record.

Expose this as one creation action when the caller does not need to control retry boundaries. Cloudinary is the default storage, delivery, thumbnail, and derivative service; it is not the default scene compositor. Do not create a base video or duration-matched carrier.

The renderer may choose technical transformation details but may not choose facts, conclusions, or new examples.

Preserve deterministic render identity/caching when supported.

## 10. Render-status handling

Track `prepared`, `rendering`, `ready`, and `failed` states. Reuse an identical prepared bundle on retry; do not regenerate narration or refetch changing source inputs.

Do not require an async job system merely for architectural purity if the current renderer reliably handles the requested output. Never report `ready` until technical QA, Cloudinary upload, and catalog persistence all succeed.

## 11. Technical QA

Inspect finished output when possible:

- file/URL loads
- dimensions/aspect correct
- narration starts and ends cleanly
- no clipped audio
- scenes appear in correct order
- no blank/stale/wrong assets
- captions visible and aligned
- overlays appear at intended moments
- transitions/motion work
- important graphic content is not cropped
- duration is sensible
- the uploaded URL identifies a persisted MP4 rather than an unmaterialized transformation

## 12. Factual QA on final render

Compare every visible/spoken substantive number or claim to the fact ledger.

Wrong property, wrong number, stale cache, or unsupported claim is blocking.

## 13. Derivative selection

Do not render every possible format automatically. Produce only derivatives justified by the story:

Typical strong investigation:

- one 16:9 long-form video when warranted
- one to three 9:16 shorts when genuinely distinct
- one static graphic/carousel when useful

Simple findings may need only one vertical video.

## 14. Distribution package

Without publishing, package conceptually:

- media assets
- selected title + alternatives
- platform-ready captions/descriptions
- thumbnail/static assets
- source notes
- target platform/format
- distribution manifest

Keep distribution separate from factual production.

## 15. Human approval

Prefer human approval before first-wave publishing. Automatic publishing is a separate explicit action requiring an appropriate connected capability.

## 16. Production disposition

End with:

- `PRODUCTION_COMPLETE`
- `PRODUCTION_COMPLETE_WITH_CAVEATS`
- `PRODUCTION_BLOCKED`

For a block, identify whether it is data/editorial, asset, narration, timing, renderer, or QA failure.

## 17. Required final package

Preserve:

- story ID
- fact-ledger reference
- approved scripts
- source package
- visual asset IDs/URLs + provenance
- narration asset + timing
- caption reference/data
- production manifests
- final media asset IDs/URLs
- dimensions/durations
- QA results
- warnings/caveats
- distribution package metadata
- durable episode catalog record visible in `/staff/house-content/`

## 18. Core production principle

The renderer executes a verified story.

It does not create the story.
