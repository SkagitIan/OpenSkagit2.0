# State and Handoff Contracts

These are conceptual contracts. Follow existing project schemas when they already provide equivalent fields.

## Investigation state

Suggested statuses:

- `candidate`
- `researchable`
- `investigating`
- `rejected`
- `validated`
- `production_ready`
- `producing`
- `complete`

## Discovery handoff

- investigation_id
- question
- homeowner_concern
- hypothesis
- alternative_hypothesis
- geography
- population
- variables
- controls
- available_capabilities
- proposed_method
- required_authoritative_context
- potential_visuals
- evidence_risks
- discovery_scores
- research_confidence

## Research handoff

- investigation_id
- research_question
- answer_summary
- surprising_finding
- evidence_grade
- storyworthiness
- fact_ledger
- sample_description
- methodology_summary
- filters/exclusions
- major_controls
- limitations
- authoritative_context
- approved_statistics
- approved_examples
- visualizable_findings
- prohibited_claims
- source_references
- disposition

## Fact ledger item

- fact_id
- statement
- classification: VERIFIED_FACT / CALCULATED_RESULT / ANALYSIS_INTERPRETATION
- value
- unit
- display_text
- narration_text
- source
- source_reference
- population_or_property_references
- calculation_or_method
- confidence
- limitations
- approved_for_public_use

## Story handoff

- story_id
- investigation_id
- question
- story_promise
- central_reveal
- hook_candidates
- selected_hook
- title_candidates
- selected_title
- master_script
- short_scripts
- script_fact_map
- visual_beats
- required_assets
- approved_overlay_text
- fact_ledger_reference
- source_package
- limitations
- prohibited_claims
- target_formats
- production_status

## Narration augmentation

- narration_asset_id
- narration_url/reference
- original_script
- aligned_transcript
- duration
- voice/model/settings
- word_timings
- segment_timings
- caption_data/reference

## Production manifest

Top level:

- manifest_id/version
- story_id
- target_format/aspect/dimensions
- scenes
- narration_asset
- captions
- optional background_audio
- render_version
- provenance

The manifest is renderer-neutral. It must not contain a required carrier/base-video field.

Scene:

- scene_id
- duration
- computed_start/end
- visual_asset_id/reference
- motion
- transition
- overlays
- evidence/fact_ids

For 9:16 production, each scene must also declare exactly one scene type:
`DATA_FULL_FRAME`, `MEDIA_FULL_FRAME`, `MEDIA_WITH_DATA_CARD`, or `SPLIT_COMPARE`.
It must contain one `primary_asset`; a data scene cannot contain an unrelated
background video. Request `presentation_mode=video_scene` from visual generators.
Captions occupy the shared bottom safe zone and are separate from data callouts.

## Final production package

- story_id
- investigation_id
- final_status
- fact_ledger_reference
- source_package
- scripts
- visual_assets
- narration_asset
- narration_timing
- captions
- manifests
- final_media_assets
- dimensions/durations
- QA_results
- warnings/caveats
- distribution_manifest

## Prepared render bundle

- bundle_id/content hash
- immutable normalized manifest
- frozen narration file
- frozen scene files
- caption SRT/ASS
- resolved contiguous timing
- preparation status and warnings

## Episode catalog record

- episode_id
- status: prepared / rendering / ready / failed
- title and description
- aspect/dimensions/duration
- Cloudinary public ID and final MP4 URL
- thumbnail URL
- normalized manifest
- technical QA results
- warnings/failure reason

Only `ready` records appear in `/staff/house-content/`. Catalog persistence is part of production completion, not a separate manual task.
