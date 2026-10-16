# First-profile chart line-width calibration

Status: proposed; implementation and profile promotion are not approved by this
document. This changes one target-specific constant in the reviewed fixed
GridCraft profile. Requirements, release gates and engineering limits stay intact.

## Observed behavior

With the official GridCraft 0.7.0 release, the candidate's requested 2-point chart
line is saved as 2.25 points (OOXML width 28575 instead of 25400). Fresh-context
reopen and a second actual Save retain 2.25 points. The original failed run is
`1569b373-c58d-4025-ada2-b9720c5258f4` under the local
`artifacts/gridcraft/task-4/profile-browser/` evidence directory.

A separate diagnostic run, `f8370898-8999-46bc-8ad8-04201ccd77e8`, changed only the
bootstrap chart width to 2.25 points. All 480 artifact comparisons at each of
bootstrap, actual Save and fresh-context reopen/resave matched. This is bounded
artifact fidelity evidence, not completion of the profile's UI, update, conflict,
installed package or integration acceptance requirements. The failed original
run remains retained. The public mapping remains untested.

## Proposed change

Change the first GridCraft profile's exact chart line width from 2 to 2.25 points.
Update its frozen theme declaration, independently expected bootstrap/save/reopen
values and canonical profile identity together. Continue rejecting other widths
for this profile. The target-neutral theme model remains unchanged; other apps
and future profiles gain no new support claim.

Use XlsxWriter for bootstrap and the actual GridCraft Save for output, with no
post-save rewrite, alternate exporter or local app build. All other fixed-profile
properties and required evidence remain unchanged. An omitted OOXML
`dispBlanksAs` element may be interpreted as its standard gap default by the
artifact oracle; retain its raw presence and independently verify the visible
chart gap as already required.

## Acceptance and approval

After independent review and owner approval, integrate this constant into task 4
and rerun the affected production mapping and actual-browser proof. The
diagnostic ZIP experiment cannot itself promote the production profile. Task 4
still requires its remaining profile and upstream RunPins acceptance; this
calibration does not mark any task complete or grant validated-report release.

No package, dependency, source owner, budget exception, new report feature or
broader supported formatting range is introduced.
