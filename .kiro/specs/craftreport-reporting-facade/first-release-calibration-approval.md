# Owner approval: first-release calibrations

On 2026-10-16 the owner answered "Approve both corrections (Recommended)" to
the explicit request covering both independently reviewed proposals below.

- Snapshot storage: aggregate 1,500 to 2,000 LLOC, with function 50, module 300
  and McCabe 10 unchanged. Reviewed proposal:
  [storage calibration](../craftreport-snapshot-runtime/storage-budget-calibration-amendment.md),
  SHA-256 `5354B5E93315E8A7395DEAA675AF43BAD0C01ED2DA132C394805E56F1B1E4237`.
- GridCraft first profile: chart line width 2 to 2.25 points. Reviewed proposal:
  [chart calibration](../craftreport-gridcraft-web-reports/line-width-calibration-amendment.md),
  SHA-256 `f7944a397e650f0b5b610f64b8e589aa390e7e368b8a4dd50f4bfe38a38a15dd`.

The original proposal files remain unchanged so their reviewed hashes remain
reproducible. This record approves the described design/task corrections, not
their implementation or feature completion. Storage task 4.0 must implement and
verify the exact enforcing gate before task 4.1 resumes. GridCraft task 4 must
update the real candidate and complete its remaining proof; the diagnostic
experiment alone cannot promote support. All other limits, ownership and release
acceptance requirements remain unchanged. No further confirmation is needed for
these two corrections.

## Category label fit correction

Later on 2026-10-16 the owner answered "Approve the bounded first-profile
correction" for the independently reviewed
[category-label amendment](../craftreport-gridcraft-web-reports/category-fit-calibration-amendment.md),
SHA-256 `79e134485806815705d7e07bf3ffe20f31534c69f162c87c802fc6fdf1e91504`.
Dynamic table/chart category labels use a maximum of 16 serialized UTF-8 bytes;
literal-text cells retain their 32-byte limit. The original proposal and review
remain historical records. This approval authorizes the actual admission/profile
pin correction and its tests, with no truncation, geometry/theme change or
acceptance waiver. Two same-document updates, actual Save/readback/reopen,
visible fit and all remaining task-4 gates are still required. The narrower-input
diagnostic alone does not establish a supported production profile.
