# First-profile category label fit calibration

Status: **proposal for independent review; no implementation or profile-promotion
approval**. Date: 2026-10-16. This proposes one target-specific admission
correction. Requirements, ownership, release gates and engineering limits remain
unchanged. The public operation profile remains untested.

## Observed failure and bounded diagnostic

The owner-approved 2.25-point candidate round-trips its selected artifact
properties, but its proposed 32-serialized-UTF-8-byte category domain fails visible
label fit in official GridCraft 0.7.0. With four categories consisting of 30 W
characters, 15 é characters, Gamma and Delta, the released chart displays the
first label and Gamma while omitting the second label and Delta. Both long labels
are exactly 32 serialized UTF-8 bytes. Table cells wrap these strings correctly;
that does not establish chart label fit.

The retained failing profile run is
`c7c04f8c-9675-4985-80c7-bfd38d00a9f7` under local
`artifacts/gridcraft/task-4/profile-browser/`. It includes two real same-document
UI updates, actual app Saves, independent XLSX inspection and fresh-context
reopen. All 480 artifact comparisons at each of five checkpoints passed, as did
selected UI text/TSV checks. Mechanical pytest reported one pass in 358.64 seconds.
The **overall 32-byte profile verdict is NO-GO** because manual visible review
found omitted labels; mechanical equality cannot override that failure. A
PowerShell console-title pipe error occurred after pytest completed and is
recorded separately from the test result and accepted resource cleanup.

A parent-authorized diagnostic kept the same actual theme, geometry, four
categories and production admission, but supplied narrower category inputs:
14 W characters, seven é characters, Gamma, Delta. The first two each occupy
16 serialized UTF-8 bytes. Literal text still exercised the 32-byte boundary,
quote/backslash text and a literal URL; numeric values were 0, 1, 9999, 5000,
with the unchanged second-category chart gap. All four chart labels were visible
after the update and after fresh-context reopen. Run
`cf993bea-2309-4477-8996-0cc88d7f78f0` retained the actual source, app-saved
bytes, 480 matching artifact comparisons at each of four checkpoints, UI
readbacks, screenshots and videos. Pytest reported one pass and one deselection
in 224.03 seconds; the command exited zero. This is a narrower-input diagnostic,
not approval of a changed profile or general text support.

Both runs used Windows headless Chromium 156.0.8078.4 at 1600x1100, the pinned
downloaded 0.7.0 archive/JS/WASM and isolated attached Debian WSL Compose hosting.
Each recorded 25 graceful and eight SDK-closed resources, decoded flushed video
and no unexpected fatal application diagnostics. Neither used an alternate
exporter, post-save repair, local Rust build or operator browser/session.

| Evidence | SHA-256 |
| --- | --- |
| Failed 32-byte update1 saved XLSX | `2dc44b60957c4c6cdbc9b8a444717ee0bd42389d196c42f9984be1e02cc62071` |
| Failed 32-byte chart screenshot | `8550ac70c74f82c46364b0e750f61cbdc47b15fa08f2c7a8e7160d6bd2b99376` |
| 16-byte diagnostic update1 saved XLSX | `2e22b068c57b468b2cbf05a7bbbe8e9fe95ac532e3179506480af0b7bffc4b5b` |
| 16-byte diagnostic fresh-context resave | `9807fe2c3d84c0b89ae60bec75b03d653d5c43cb94e33652c4cebcadf4574dbb` |
| 16-byte diagnostic chart screenshot | `0030d28039294514cc0c5252d77b262d901c5866ded0e5c07ff70fb5db9993e6` |

## Proposed correction

Limit dynamic category text to **16 serialized UTF-8 bytes per value**, measured
by the existing canonical string-size rule (`json.dumps(value,
ensure_ascii=False).encode("utf-8")`). Apply the same limit to the table category
column and its equal independent chart category source. Retain **32 serialized
UTF-8 bytes** for the literal-text column. Preserve the existing excluded Unicode
categories, literal treatment, no coercion/truncation, schema/order equality,
numeric 0..9999 candidate domain and all other bounds and unsupported statuses.

This changes admission rather than silently shortening, dropping or relabeling
supplied categories. A category exceeding 16 bytes must produce the typed limit
issue at its affected location before app input. A literal value above 32 bytes
continues to reject separately. Neither dimension establishes support until its
remaining real-effect evidence passes.

Keep the exact theme, including the approved 2.25-point line, and existing chart
geometry. The actual chart top-left anchor is A18 and its retained end is F35
plus offsets, fully contained in reserved A18:H38. Its exact OOXML
from/to/off tuple is `(0,0,17,0,5,161925,34,57150)` in cells/EMUs. Unused reserved
cells remain unused; do not stretch the chart or alter labels to avoid the fit
failure. This is not an additional report shape or a broader formatting profile.

After approval, update the canonical profile declaration/digest to distinguish
the category and literal limits. Update admission, independent boundary/rejection
expectations and disclosed profile limits together. The frozen theme/presentation
stays unchanged because this correction changes no style value. Do not publish
the diagnostic under the old profile pin as evidence that the 32-byte domain
works, and do not weaken report-model's supplied-descriptor semantics.

## Prospective visible regression and acceptance

A small profile-bound visible-label oracle can supplement manual review. In the
retained screenshots, horizontal chart frame/axis bands identify the label
baseline; require visible dark label ink near the independently fixed fourth
category center for the unchanged nonempty label Delta. At the failed image's
baseline, x475:520/y574:585 contains zero dark neutral pixels; the corresponding
16-byte image contains 45. First/Gamma label regions are positive controls.
The failed image must fail the proposed oracle; the diagnostic and fresh-reopen
image must pass it. Keep the raw screenshot and measured regions.

This is a regression for the demonstrated thinning case, not OCR or proof of all
label text. Other glyphs, overlays, selection borders or chart movement can cause
false positives or negatives. Validate target identity, dimensions, fixed drawing
geometry and unobscured chart first; do not accept an arbitrary dark mark as the
expected label. Continue independently inspecting all four source categories and
manually reviewing full-label visibility/fit. Exact pixel-color, typography or
cross-platform equivalence is not newly promised by this proposal.

Independent review and owner approval must precede the actual profile/admission
change. Then freeze the updated candidate, prove 16-byte ASCII/non-ASCII/escaped
boundaries and above-limit rejection, retain 32-byte literal cases, repeat both
same-document updates and actual Save/independent inspection/fresh reopen, and
verify exact chart/outside signatures. Carry the visible fit verdict separately
from artifact comparisons and retain the original failed 32-byte evidence.

This proposal does not close task 4. Installed-package proof, any remaining
applicable summary/presentation evidence and accepted snapshot-runtime 5.1 for
RunPins-consuming integration remain gates. Quality acceptance continues to use
the actual evaluator-produced paired summary; a constructor-only maximum-length
layout diagnostic cannot imply policy support. Later guarded operations, controls,
publication, validated release, quickstart/demo and headed verification retain
their separate gates. No budget exception, dependency, owner or upstream contract
change is proposed.
