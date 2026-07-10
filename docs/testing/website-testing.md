# ReliefQueue AI Website Testing Overlay

This project follows the cross-project website/frontend validation playbook:

```text
/home/ankur-sawhney/gitlabRepos/ai-career-sprint/daytona-cloud/docs/Website_Testing_Guidelines.md
```

Do not duplicate the full playbook here. Keep this file focused on ReliefQueue-specific routes, hard failures, and safety rules.

## Project routes to validate

Validate the exact routes the user/demo operator opens, not only internal or legacy routes.

Current route matrix to keep current:

| Route | Expected surface | Notes |
| --- | --- | --- |
| `/` | Landing/product entry surface | Must not contain dead primary actions. |
| `/dashboard` | User-facing dashboard route | Should resolve to the intended polished dashboard unless explicitly documented otherwise. |
| `/dashboard?source=latest` | Latest-data/polished dashboard route | Must not show product API unavailable banners or dead command controls. |
| `/dashboard/overview` or equivalent Overview section | Command Center overview | Reachable from sidebar and tiles; should show summary + drilldowns. |
| `/dashboard/map` or equivalent map panel | Live operations map | Reachable from map/zone/pin affordances. |
| `/dashboard/assignments` and assignment detail panel/route | Task assignment board | Reachable from sidebar, case cards, assignment tiles, and relevant buttons. |
| `/dashboard/field-sync` | Field sync/outbox status | Reachable from sidebar and sync/status affordances. |
| `/dashboard/scenario` | Scenario settings/profile controls | Reachable from sidebar and scenario controls. |
| `/dashboard/ai-control` plus test/confirm surfaces | AI configuration/model testing/change confirmation | Reachable from sidebar and AI/provider cards/buttons. |
| `/dashboard/quality` | Quality review queue | Reachable from sidebar and human-review/duplicate/missing-info tiles. |
| `/dashboard/audit` plus audit detail panel/route | Audit/troubleshooting | Reachable from sidebar, debug affordance, and audit/event rows. |
| `/field/my-cases` | Field Coordinator mobile case list | Must be reachable from printed Field Coordinator URL. |
| `/field/cases/:caseId` or equivalent case detail | Field case detail | Reachable from field case cards/rows. |
| `/field/outbox` and sync-conflict surfaces | Field offline outbox/sync conflict review | Reachable from field sync/outbox affordances. |
| `/internal/classic-dashboard` | Internal/legacy dashboard, if retained | Keep legacy/classic view separate from the user-facing route. |
| `/internal/classic-dashboard?source=latest` | Internal/legacy latest-data view, if retained | Internal only; do not use as proof that the polished route works. |

If a route does not exist yet, mark it as `not implemented` in the route matrix rather than silently skipping it.

## ReliefQueue hard failures

Fail website/demo validation on any of the following unless explicitly allowlisted with a reason:

- `Product API unavailable`
- `overview 404`
- any unexpected `/api/product/...` 404/500
- browser console error during route load or button click
- click action with no visible state change, toast/status, modal/drawer/navigation, audit entry, disabled explanation, or recoverable error
- command-centre action that implies automatic real-world dispatch without coordinator approval
- command-centre action that does not visibly state suggestion/demo/approval status
- polished dashboard route showing the classic dashboard unintentionally
- sidebar/navigation clicks that only change the blue title/active state while the main product body does not meaningfully change
- role/source/dropdown changes that do not visibly change data, mode, permissions, preview, or explanation text
- cards, metric tiles, map pins, chips, status badges, table/case rows, or input-looking debug badges that appear clickable but are neither wired nor clearly styled/classified as static
- operator instructions that reference a non-existent command or make target
- `connection refused`, `Address already in use`, or stale-port errors in the operator-facing dashboard startup path
- removing hand-cursor, pointer, card, tile, map-pin, or hyperlink navigation affordances instead of wiring them
- any hand-cursor/pointer affordance that does not navigate, open details, apply a filter, focus a panel, or perform a visible safe action
- Command Center reference/generated screens that are present as code/design but not reachable from the user-facing dashboard
- Field Coordinator reference/generated screens that are present as code/design but not reachable from the field/mobile route
- screens/routes that render placeholder-only or duplicate generic content instead of logical ReliefQueue data/content
- tests claiming button coverage without a click manifest and artifact review
- rendered hand-cursor affordances that are present in inventory but not clicked, grouped, disabled, or deferred
- representative click coverage being claimed as exhaustive without an equivalence-group matrix
- `static_visual` or `informational` classifications for elements that still show a hand cursor or pointer styling
- strict guard warnings from broad aliases or ambiguous screen matches being treated as a clean pass
- raw Stitch/AI Studio/design zips being used for a large run without a generated reference digest and screen-to-route map
- negative strict-guard fixtures aborting setup before being classified as expected failures
- result validation depending only on the original input bundle for strict guard/contract files
- reporting a clean pass when `unresolved_interactive_count` is non-zero or strict-guard warnings are unresolved
- treating hundreds of raw DOM affordances as either all resolved or all unresolved without a canonical-affordance rollup
- accepting a dashboard/mobile route that technically loads and clicks but has no meaningful vertical depth, no scrollbar where a dense operational screen is expected, or too little screen-specific content for a hackathon demo
- treating `few_rich_source_files_detected` or rich AI Studio adaptation concentrated in `dashboard/src/visualApps.jsx` as a clean pass after the user has rejected that architecture
- applying a visually rich but monolithic AI Studio adaptation as final when the requested state is maintainable Command Center and Field Coordinator modules
- preserving an inferior old frontend, stale compatibility layer, duplicate classic/polished surface, or monolithic route file only because it already exists
- treating compatibility with the current frontend implementation as a requirement after the user has said best result matters more than preserving compatibility


## Navigation preservation requirement

For ReliefQueue, tiles, cards, map pins, case rows, role/source controls, debug controls, and sidebar items are valid navigation/action affordances when the browser shows a hand cursor or the design looks clickable.

Do not remove navigation, cursor-pointer styling, hover affordances, or clickable card behavior to make validation pass. The expected fix is to wire the affordance to one of:

- logical route
- detail page
- drill-down drawer
- modal/panel
- filter/focus state
- safe demo action result with coordinator-review copy

If a future run believes an affordance should become static, it must stop and request human approval rather than silently downgrading the UI.


## Visual richness and hackathon demo readiness

ReliefQueue is being prepared for a judged hackathon demo. A technically green route/click run is not enough if the manually opened portal looks stripped down, has no meaningful scroll depth, or fails to communicate the product story.

For the main demo routes, validation should produce a `visual-richness-summary.json` and screenshots. Required routes include at least:

```text
/dashboard?source=latest
/dashboard/amd-impact
/dashboard/capability-map
/dashboard/map
/dashboard/assignments
/dashboard/field-sync
/field/my-work
/field/my-cases
/field/outbox
```

Each route summary should include:

```text
route
screenshot_path
viewport_height
scroll_height
has_vertical_scroll
section_count
card_or_panel_count
table_or_list_count
map_or_spatial_panel_count
primary_action_count
screen_specific_content_markers
hackathon_story_value
```

For Command Center routes, the visible surface should make the relief-operations story obvious: live flood/incident context, open needs/cases, assignment pressure, field sync state, AI/vLLM advisory status, human review boundaries, AMD impact, and capability/runtime honesty.

For Field Coordinator routes, the visible surface should look like a real mobile workflow: assigned work, case detail, status update, notes, new request, offline outbox, sync conflicts, and network/help state.

A route that has only a few generic tiles or no below-the-fold content should be marked `visual_needs_rework` even if it passes click checks.


## Best-result-over-compatibility frontend policy

For ReliefQueue frontend work, the user prefers the best product/demo result over preserving compatibility with the current frontend implementation. This is a standing policy unless the user explicitly scopes a future task as a compatibility-only hotfix.

Do not constrain Codex or future implementation agents to “preserve the current frontend and add to it.” They may patch, refactor, delete, or replace the current dashboard/mobile implementation when that produces a better ReliefQueue Command Center or Field Coordinator experience.

The stable contract is:

```text
- the main user/demo entry routes remain clear or redirect with ownership
- the product story is stronger and more useful in browser/manual review
- actions remain safe, demo/suggestion-oriented, and coordinator-reviewed where relevant
- AMD/vLLM/fallback state remains honest
- validation evidence is stronger, not weaker
- source architecture is cleaner and more maintainable
```

The old frontend shape is not a contract. Avoid keeping:

```text
- duplicate classic and polished dashboards competing for ownership
- compatibility wrappers without a current user-facing reason
- stale aliases or legacy paths as proof of implementation
- one-file visual monoliths created only to minimize patch size
- old surfaces that make the demo weaker, thinner, or harder to understand
```

For major frontend runs, the prompt and guard should explicitly include:

```text
BEST_RESULT_OVER_COMPATIBILITY=true
CURRENT_FRONTEND_IS_NOT_A_CONSTRAINT=true
CODEX_MAY_REPLACE_OR_REBUILD_FRONTEND=true
NO_COMPATIBILITY_LAYERS_BY_DEFAULT=true
REMOVE_DUPLICATE_OR_STALE_SURFACES=true
```

If a run chooses to retain legacy/internal routes such as `/internal/classic-dashboard`, it must explain why they still help and keep them clearly separate from the judged/product route.

## Modular AI Studio adaptation requirement

The real AI Studio Command Center and Field Coordinator exports are source material, not just route-name inspiration. A successful ReliefQueue adaptation should preserve meaningful screen boundaries in the source code unless a temporary prototype is explicitly approved.

It may replace the current frontend rather than preserving it. Do not force the generated/reference screens to fit the old `visualApps.jsx` structure if a clean Command Center / Field Coordinator source tree would produce a better result.

Do not accept another result where the rich adaptation is concentrated primarily in:

```text
dashboard/src/visualApps.jsx
```

The desired direction is:

```text
dashboard/src/visualApps.jsx                # thin route/shell/orchestrator only
dashboard/src/visual/commandCenter/         # command-center shell, data, and view modules
dashboard/src/visual/commandCenter/views/   # overview, map, assignments, workload, field sync, scenario, AI control, quality, audit, intake, incident links, AMD impact, capability map
dashboard/src/visual/field/                 # field shell, data, and mobile screen modules
dashboard/src/visual/field/screens/         # my work, case list, detail, status, note, new request, outbox, conflicts, help
```

Future ReliefQueue visual repair guards should fail unless they can report something like:

```text
rich_source_files_detected >= 10
command_center_view_files_detected >= 8
field_screen_files_detected >= 6
visualApps_thin_shell=true
monolithic_visualApps_adaptation=false
strict_guard_warning_count=0
```

If a run creates a visually useful but monolithic implementation, classify it as:

```text
PRODUCT_VISUAL_VALIDATION_STATUS=PASS
SOURCE_ARCHITECTURE_STATUS=FAIL
FINAL_REVIEW_STATUS=NEEDS_REWORK
```

Use that result as a seed for a modular repair run rather than applying it as final.

## Reference screen integration expectations

ReliefQueue has generated/reference material for both the Command Center website and Field Coordinator mobile app. Future frontend completion runs should produce a screen coverage matrix and make the logical content reachable.

Command Center screen families to cover or merge into equivalent reachable surfaces include:

- overview/dashboard summary
- live operations map
- task assignment board
- coordinator workload
- field sync status
- AI configuration
- AI model test
- AI change confirmation
- scenario settings
- quality review queue
- audit dashboard
- audit/troubleshooting detail

Field Coordinator screen families to cover or merge into equivalent reachable surfaces include:

- sign-in or role selection
- my work dashboard
- assigned case list
- case detail
- update case status
- add field note
- new relief request
- offline outbox
- sync conflict review
- network/help/status surfaces

Each screen family must be `implemented`, `merged_into_equivalent`, or `deferred_with_reason` in the screen coverage matrix. For the next completion run, prefer implemented/merged over deferred.



## Reference digest requirement for large UI runs

Before another large ReliefQueue Command Center or Field Coordinator Codex run that uses Stitch, AI Studio, screenshots, or generated design exports, prepare a digest first rather than sending only raw zips.

Expected digest files:

```text
context/reference-screens/extracted/
context/reference-screens/reference-screen-index.json
context/reference-screens/reference-screen-digest.md
context/reference-screens/screen-to-route-map.csv
context/reference-screens/component-to-screen-map.csv
context/reference-screens/affordance-contract-seed.json
```

The digest should preserve exact raw export names from Stitch/AI Studio and map them to ReliefQueue routes or surfaces. The user should only need to review the route/screen map, not re-explain every screen manually.

## Latest artifact-review lessons to preserve

The screen-routing run was a substantial improvement, but review found an important evidence gap: the rendered hand-cursor inventory can be much larger than the clicked-control manifest. Future ReliefQueue validation must reconcile the two.

Required summary fields:

```text
rendered_affordance_count=
interactive_affordance_count=
clicked_affordance_count=
disabled_with_reason_count=
static_without_pointer_count=
representative_group_count=
unclicked_interactive_count=
strict_guard_warning_count=
```

A run is not complete merely because representative controls passed. Every hand-cursor/pointer affordance must be either individually clicked, covered by a named equivalence group with the same handler/destination/data shape, disabled with visible reason, or explicitly deferred. If evidence shows hundreds of rendered affordances but only a small subset clicked, final review should be `NEEDS_REVIEW` until the gap is explained.

`static_visual` is acceptable only when the element does not show hand-cursor/pointer navigation affordance. If the browser shows a hand cursor, wire it; do not classify it as static.

Strict guard warnings must be reviewed. Broad aliases such as `network`, `help`, `status`, `assignment`, or `worker` should not be enough to prove screen coverage. A strict guard pass with broad-alias warnings is not a clean final pass.


## Codex campaign and harness expectations for ReliefQueue frontend work

Future ReliefQueue frontend Codex runs should use a campaign model when the backlog is large:

```text
issue-ledger first
→ class-level fixes
→ FAST validation
→ bounded self-repair
→ FULL validation
→ self-contained result archive
```

Expected additional artifacts:

```text
reports/website-readiness/latest/issue-ledger.json
reports/website-readiness/latest/affordance-coverage-reconciliation.json
reports/website-readiness/latest/equivalence-groups.json
reports/website-readiness/latest/remaining-work-ledger.json
```

ReliefQueue-specific clean-pass criteria:

```text
unresolved_interactive_count=0
strict_guard_warning_count=0 or every warning has explicit evidence/reason/follow-up
static_visual_with_pointer_count=0
reference_screens_missing_or_unreachable=0 unless deferred-with-reason is approved
result_validate_self_contained=true
```

If these are not true, the result may still be useful, but the final status should be `partial_pass_needs_followup` or `NEEDS_REVIEW`.

### Harness regression lessons

Recent Daytona input-bundle iterations exposed two harness failure patterns that must not recur:

1. A negative strict-guard fixture correctly failed, but the setup script treated the expected non-zero exit as `SETUP_STATUS=FAIL` before Codex started.
2. A result validation script required the original input bundle's guard path, so trusted-target validation failed when that input bundle was not extracted.
3. A reviewed patch failed because the trusted local checkout had drifted from the Daytona baseline; an exact-file overlay with precheck/backups was safer than forcing a fragile patch hunk.
4. A safe overlay correctly refused to overwrite a dirty target file; this should be treated as an apply-safety stop, not a product validation failure.
5. Split result/fallback archives must be checked for missing parts before reconstruction; compare normal and fallback patch hashes/diffstats before assuming they differ.

For ReliefQueue, future bundles must:

```text
- wrap negative fixture checks in explicit if/else classification
- print STRICT_GUARD_NEGATIVE_FIXTURE_STATUS=PASS rejected_bad_fixture when expected
- keep setup/clone/dependency/preflight in foreground before tmux/Codex
- include strict guard, contract, schema, and reference digest inside the result archive
- let validate.sh find its own validation files before falling back to INPUT_ROOT
- classify harness/setup failures separately from product failures
- for reviewed overlays, print dirty target file status and require an explicit override such as `ALLOW_DIRTY_TARGET_FILES=1` only after backups are captured
- reconstruct split archives only after all numbered parts are present and tar-readable; if normal and fallback patches are identical, do not treat fallback as a different implementation
- for fresh Daytona runs that clone latest Git, do not include collect-context scripts by default; add them only for uncommitted local changes, local-only evidence/logs, diagnostics, or explicit user request
```

### Canonical affordance rollup

ReliefQueue dashboards contain cards, badges, nested text/icons, map pins, rows, and action buttons. The rendered raw affordance count can be high because one visible card may contain many DOM descendants.

Future reports should include both raw and canonical counts:

```text
raw_rendered_affordance_count=
canonical_affordance_count=
interactive_canonical_affordance_count=
clicked_canonical_affordance_count=
equivalence_group_covered_count=
unresolved_canonical_affordance_count=
```

A parent card and a child action button must not be merged if they perform different actions. Nested spans/icons may be grouped under the parent only when they share the same click target and outcome.


## ReliefQueue safety copy expectations

ReliefQueue command actions are demo/suggestion workflows unless explicitly configured otherwise.

Actions such as assignment, dispatch, queue messaging, status change, replay, retry, escalation, or resource allocation should visibly communicate one of:

- suggestion created
- coordinator approval required
- queued locally for demo
- simulated/demo-only
- config/API unavailable with local fallback
- disabled because prerequisite/config is missing

Avoid copy that implies real emergency dispatch occurred automatically.

## Required click outcomes for known controls

Keep this table current as controls are added/removed.

| Control family | Example labels | Required visible outcome |
| --- | --- | --- |
| Assignment actions | `Assign Alpha`, `Assign Bravo`, similar | Assignment suggestion/status appears, selected case/resource state updates, and activity/audit entry is added. |
| Status actions | `Set in progress`, `Resolve`, similar | Case status visibly changes or recoverable error/fallback appears. |
| Messaging actions | `Queue message`, `Send update`, similar | Message draft/queued status appears and activity/audit entry is added. |
| Left navigation/sidebar | `Overview`, `Assignments`, `Field Sync`, `Scenario`, `AI Control`, `Quality`, `Audit` | Main body must show a real section-specific panel/table/list/cards and not only change the blue title or active pill. |
| Role/source dropdowns | top-right role selector, source selector, scenario selector | Selected value must visibly change data, mode, permissions, preview text, or show a clear preview-only/no-effect explanation. |
| Metric tiles and cards | `Open cases`, `Critical`, `Field units`, `Human review`, case cards | Either open/filter/focus a drill-down detail or be clearly static/non-clickable. |
| Map/chip/status affordances | map pins, zone chips, badges, timeline/status chips | Either focus/filter/show details or be clearly static/non-clickable. |
| Debug-looking controls | `Internal debug`, runtime/debug pills | Either open a debug/details panel or be restyled as static status text. |
| Filters/source controls | Source/latest/filter controls | Results, chips, empty state, or explanation visibly changes. |
| Provider/runtime controls | AI/vLLM/GPU/provider buttons | Visible config-needed, demo fallback, or runtime status explanation appears. |
| Disabled controls | Any disabled action | The reason for disabled state is visible or discoverable without guessing. |

## Required artifacts for ReliefQueue frontend validation

Preferred report folder:

```text
reports/website-readiness/<timestamp>/
```

Expected contents when Playwright/browser validation is run:

```text
route-matrix.json
command-center-route-matrix.json
field-app-route-matrix.json
screen-coverage-matrix.json
navigation-map.json
hand-cursor-affordances.json
reference-screen-digest.md or reference-screen-index.json  # when design/reference exports are in scope
equivalence-groups.json or affordance-coverage-reconciliation.json
issue-ledger.json
remaining-work-ledger.json
affordance-coverage-reconciliation.json
canonical-affordance-inventory.json
click-manifest.json
console.log
page-errors.json
network-summary.json
failed-requests.json
har/
traces/
screenshots/
```

Validation summaries should report:

```text
Routes tested:
Controls tested:
Raw rendered affordances:
Canonical affordances:
Interactive canonical affordances:
Clicked canonical affordances:
Representative equivalence groups:
Unclicked interactive affordances:
Strict guard warnings:
Console errors:
Page errors:
Unexpected 4xx/5xx:
Product API unavailable banners:
Title-only/active-only nav changes:
Dropdowns with no visible effect:
Unclassified clickable-looking cards/tiles/pins:
Hand-cursor affordances not wired:
Reference/generated screens unreachable:
Command Center screens reachable/total:
Field Coordinator screens reachable/total:
Startup connection/port/missing-command issues:
Dead-click candidates:
Artifacts:
```

A green test run without artifact review is not enough.

## Manual repair loop for current dashboard issues

When debugging click-responsiveness, use one control at a time:

1. Open the exact user-facing route, especially `/dashboard?source=latest` when testing latest-data dashboard behavior.
2. Click one visible control, for example `Assign Alpha`.
3. Record visible result, failed requests, and console errors.
4. Fix the full path for that action: frontend handler, API/demo facade, fallback, visible result, and audit entry.
5. Add/adjust a Playwright regression test that proves the visible result and records artifacts.
6. Move to the next control only after the current one is verified.

Do not accept a broad “all buttons clicked” claim unless the click manifest proves visible outcomes.

## Current manual failure patterns to prevent

Recent manual validation found a false-green gap after automated checks passed. Future ReliefQueue frontend work must explicitly guard against these patterns:

- left sidebar selections appeared to change only the blue title/active state, while the main product body did not meaningfully change
- the top-right role dropdown changed selection but did not visibly change data, permissions, preview, or explanation
- metric tiles, cards, map areas, and possible hyperlink-like affordances looked like drill-down points but were not connected to visible behavior
- user explicitly does not want these navigation affordances removed; they should be wired to logical data/content/screens
- a later artifact review showed that a run can inventory far more hand-cursor affordances than it clicks; future runs must reconcile inventory versus click evidence
- `static_visual` classification is not acceptable for any element that still shows a hand cursor/pointer affordance
- guard warnings from broad aliases can hide weak screen matching and should keep the run in `NEEDS_REVIEW` until resolved
- future large UI runs should start from a generated reference digest so Codex does not waste time rediscovering raw Stitch/AI Studio exports
- earlier v2-style harness failures happened before Codex started; future bundles must classify negative fixture rejection as preflight PASS
- trusted-target validation should not depend only on an old input bundle path for strict guard files
- future reports should separate raw DOM affordance counts from canonical user-visible controls
- generated Command Center and Field Coordinator screens existed as references but were not reachable from the current dashboard/field routes
- a later visual uplift proved that the portal can become richer while still being architecturally unacceptable because the adaptation remained concentrated in one source file
- a non-failing strict guard warning is not good enough when it names a pattern the user explicitly does not want
- result and fallback archives can be huge because they contain screenshots/traces/HAR/evidence; inspect patch/diffstat and changed-files snapshots before assuming source size or coverage
- fresh sandbox input bundles should normally be just the input archive plus start script; collector scripts are not default when latest Git clone is the source of truth
- future frontend bundles should confidently pursue a clean rebuild when that is better, not default to compatibility-preserving patching
- startup output mixed useful URLs with product API `connection refused` / `Address already in use` errors, making the operator path confusing

Do not call a run complete only because the product API endpoints return 200 or because 14 declared command buttons passed. The rendered public page must be audited for every affordance that a normal website user would try to click.

## Project-specific API boundary to monitor

Current product/dashboard flows should monitor endpoints under:

```text
/api/product/
```

Known endpoint families that must not silently fail in demo/product mode:

```text
/api/product/command/overview
/api/product/command/assign
/api/product/monitoring
/api/product/messaging/status
```

If an endpoint is intentionally unavailable, the UI must show a clear disabled/config-needed or local-demo fallback state.

## Operator-facing dashboard startup

The normal local operator path should print and serve the intended user-facing route cleanly.

Current expected route:

```text
http://127.0.0.1:5173/dashboard?source=latest
```

Startup validation should fail or clearly mark incomplete if the command output contains unhandled:

```text
Connection refused
Address already in use
OSError: [Errno 98]
No rule to make target
```

If a stable port is already in use, the command should either reuse the owned service safely, stop/replace it with a clear message, or choose/log a free port. It should not continue with contradictory "API unavailable" or crash output while the UI appears partially ready.

## Reminder for future agents

Before any ReliefQueue frontend/dashboard patch is accepted, read this overlay and the canonical guideline. Then prove:

- the route tested is the route the user opens
- click controls have visible outcomes
- rendered affordances include navigation, dropdowns, tiles, cards, map pins, chips, debug/status badges, and case rows
- hand-cursor/pointer affordances are wired and not removed/downgraded
- Command Center and Field Coordinator reference screens are reachable, merged into equivalent screens, or explicitly deferred with reason
- navigation/dropdown/card interactions produce meaningful body/data/detail changes, not only title or active-state changes
- console/network artifacts were exported and reviewed
- `/api/product/...` failures are absent or explicitly handled
- dashboard startup output is free of connection-refused/address-in-use/missing-target contradictions
- rendered hand-cursor inventory is reconciled with clicked controls, equivalence groups, disabled controls, and deferred items
- raw rendered affordances are rolled up into canonical user-visible controls without hiding distinct nested actions
- product validation, harness status, artifact review, and final review are reported separately
- result validation is self-contained and does not require the original input bundle except as an optional override
- strict guard warnings are zero or explicitly justified; broad-alias and monolithic-adaptation warnings do not count as clean pass
- visual richness is proven through screenshots/scroll depth/content density, not only route existence or click count
- AI Studio adaptation is modular enough for continued work, not concentrated in a single large route file unless explicitly accepted as a throwaway prototype
- best-result-over-compatibility is respected: old frontend code, wrappers, and legacy surfaces are retained only when they improve the final product
- fresh-clone Daytona handoffs do not include collector scripts unless a stated context-only need exists
- reference digest exists before large design/reference-screen Codex runs
- safety copy preserves suggestion/coordinator-review boundaries

## July 2026 AI Studio rescue lessons to preserve

The July 2026 AI Studio frontend rescue proved that the user-facing browser surface can be correct even when the path to it involved several harness, packaging, and wrapper failures. Preserve these lessons for future ReliefQueue frontend work.

### Purposeful screenshot policy

Screenshots are not decorative evidence. Do not take or archive screenshots only to make a result package look richer.

Take screenshots only when they will be visually reviewed by a human reviewer or by an explicit visual guard for one or more of:

- layout, styling, density, scroll depth, or visual richness;
- raw/unstyled HTML, missing Tailwind/native generated UI styling, or wrong theme;
- blocking modals/backdrops/overlays;
- missing Command Center or Field Coordinator sections;
- reference-screen alignment against Stitch/AI Studio/generated designs;
- before/after proof for an important interaction.

If screenshots are taken, the validation summary must state what was visually checked and where the reviewed screenshots live. A run that captures screenshots but never inspects them should not receive stronger evidence credit.

### Browser-computed styling is required for generated UI

For AI Studio/Stitch/generated UI adaptations, source CSS and build output are only preflight signals. The browser must prove native styling is active through computed or rendered evidence such as flex/grid, rounded corners, padding, non-white backgrounds, screen-specific content, and screenshots that are actually reviewed.

A grep showing Tailwind classes or a successful Vite build is not enough.

### Modal and overlay lifecycle coverage

Intentional onboarding, judge walkthrough, help, or confirmation modals must be tested as part of the user flow. Validation should prove:

- the modal is intentionally reachable;
- it has a visible close/continue/dismiss path;
- Escape or another expected close path works when appropriate;
- the backdrop does not intercept later clicks after close;
- downstream controls such as `Raw Intake` and `AI-Enriched Queue` remain clickable.

A blocking `.fixed inset-0` backdrop after close is a hard failure.

### Printable hard-copy operational views

ReliefQueue must not assume every Local Coordinator, Command Center Operator, or Field Coordinator can keep using a mobile/browser screen in the field. If required, any role involved in field operations should be able to print or export relevant information for hard-copy use.

Minimum printable surfaces to consider:

- field case sheet;
- assignment roster;
- priority needs list;
- offline outbox or pending sync list;
- volunteer/resource dispatch or handoff sheet;
- incident/map summary;
- coordinator shift handover summary;
- AMD/vLLM impact summary for judges/operators.

A first implementation can be simple browser print support:

```text
Print button on relevant screens
@media print stylesheet
printed_at timestamp
case/assignment/status/zone/priority fields
no secrets or raw private text in public/field print views
safety copy that preserves suggestion/coordinator-review boundaries
```

### Setup and operator onboarding are product readiness

A ReliefQueue demo is incomplete if a new operator cannot set it up from the repository without chat history. The repo should keep a clear setup path, preferably in `SETUP.md` or the main README, covering at least:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]" || python -m pip install -e .
npm --prefix dashboard install
npm --prefix dashboard exec playwright install chromium
make test
make run-demo-local AI_MODE=mock
npm --prefix dashboard run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

The expected browser routes should be printed clearly:

```text
http://127.0.0.1:5173/dashboard?source=latest
http://127.0.0.1:5173/field/my-work
```

For live-stack and AI/vLLM flows, setup docs should mark what is optional, what requires Docker or provider credentials, and what is safe/local mock mode.

### Route-wrapper tidy after rescue

Do not destabilize a newly rescued frontend by immediately renaming or deleting route wrappers only because an old note mentions them. The acceptance condition is the rendered product surface and validated user workflow, not the wrapper/import name.

For example, if `/field/my-cases` renders the intended Field Coordinator surface and browser evidence passes, an intermediate wrapper such as `FieldWorkerRoute` or an unused import is a tidy/refactor concern, not a release blocker. Clean it in a separate small pass after the working state is committed and validated.
