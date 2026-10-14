# Fixed browser-verification fixture

This internal synthetic fixture supplies the independently specified input and
oracle for `craftreport-browser-verification` task 1.3 (requirements 3.1, 3.4,
4.5 and 8.2). It contains no real financial data. The complete browser example,
visible edit, actual Save, fresh-page reopen and cleanup remain later tasks.

`reference.xlsx` is 7,559 bytes. Its SHA256 is
`7a0583c2418c988c4ec1d261e503b30c45aae3f77bc0fc548886fee4cc591ca8`.
`expected.json` schema version 1 freezes the original input hash and the typed
before/after expectations. The input hash identifies only this fixture, never
an expected edited download; saved XLSX files are compared semantically.

## Independent expectations

The only worksheet is `Report`. Only the following cells contain values:

| Cells | Stored type | Before | After |
| --- | --- | --- | --- |
| A1, B1 | string | Period, Value | unchanged |
| A2:A4 | string | Q1, Q2, Q3 | unchanged |
| B2:B4 | number | 10, 20, 30 | 10, 25, 30 |
| D1 | string | craftreport-browser-reference-v1 | unchanged |
| D2 | string | KEEP | unchanged |
| D3 | number | -7 | unchanged |

The single edit changes only numeric B3 from 20 to 25. Every other populated
cell is a sentinel. A1 and B1 are bold. B2:B4 and D3 use the Excel integer format
`0` (built-in number-format ID 1); integer display does not replace numeric storage.

There is one standard line chart, anchored at F2 with zero pixel offsets and a
480 by 300 pixel extent. Its literal title is `Reference series`; its single
literal series name is `Value`. Categories reference `Report!$A$2:$A$4` and values
reference `Report!$B$2:$B$4`. The legend is visible at the bottom (`b` in OOXML),
with overlay false; omission of the overlay element means its default false.
The value axis uses format `0`. The input chart caches Q1/Q2/Q3 and 10/20/30.
Chart source references are the only formula-like XML content: there are no
worksheet formulas, macros or external relationships/links.

The manifest's `before` and `after` maps contain `{type, value}` entries for all
populated cells. `marker`, `sentinels` and `edit` identify the observation targets.
`chart` and `presentation` describe the same single chart and cell styles.
Future inspection must follow workbook, worksheet, drawing, chart and style
relationships and accept equivalent string/reference encodings, rather than
require the input's ZIP ordering, relationship IDs or byte identity.

## Authoring provenance and reproduction

The fixture was prepared on 2026-10-14 with CPython 3.12.10 on Windows using
the Design-approved one-time **XlsxWriter 3.2.9** authoring tool. Its package was
installed by `uv` in an isolated `--no-project --with` environment. No project
dependency, lockfile or runtime XLSX writer was added. Workbook core properties
use a fixed creation time of `2026-10-14T00:00:00Z`, title
`CraftReport browser reference` and author `CraftReport synthetic fixture`.

The cells and expectations were specified from the approved Design and written
before authoring the XLSX. No GridCraft candidate output defined them. A separate
standard-library `zipfile`/`ElementTree` audit read the actual saved bytes, followed
their relationships and verified all populated cells/types, the single-cell
after delta, marker, bold fonts, integer formats, line-chart title/series/bindings,
legend, F2 anchor and extent, and absence of worksheet formulas/external links.
The first audit failed because the XLSX did not exist; the post-authoring audit
passed. Local one-time scripts and RED/GREEN/authoring logs are retained under
ignored `artifacts/browser-verification/task-1.3/`, outside the runtime harness.

To reproduce the input, save the following as a temporary `author_fixture.py`.
Run it from the repository root, using a new output path; it refuses overwrite:

```powershell
uv.exe run --no-project --with XlsxWriter==3.2.9 --python .venv/Scripts/python.exe python author_fixture.py
Get-FileHash reference.reproduced.xlsx -Algorithm SHA256
```

```python
from datetime import datetime, timezone
from pathlib import Path
import xlsxwriter

assert xlsxwriter.__version__ == "3.2.9"
destination = Path("reference.reproduced.xlsx")
assert not destination.exists(), "Author only a new fixture; never overwrite"
with xlsxwriter.Workbook(destination) as workbook:
    workbook.set_properties(
        {
            "title": "CraftReport browser reference",
            "author": "CraftReport synthetic fixture",
            "created": datetime(2026, 10, 14, tzinfo=timezone.utc),
        }
    )
    sheet = workbook.add_worksheet("Report")
    bold = workbook.add_format({"bold": True})
    integer = workbook.add_format({"num_format": "0"})
    sheet.write_string("A1", "Period", bold)
    sheet.write_string("B1", "Value", bold)
    for row, (category, value) in enumerate(zip(("Q1", "Q2", "Q3"), (10, 20, 30)), start=1):
        sheet.write_string(row, 0, category)
        sheet.write_number(row, 1, value, integer)
    sheet.write_string("D1", "craftreport-browser-reference-v1")
    sheet.write_string("D2", "KEEP")
    sheet.write_number("D3", -7, integer)
    chart = workbook.add_chart({"type": "line"})
    chart.add_series(
        {
            "name": "Value",
            "categories": "=Report!$A$2:$A$4",
            "values": "=Report!$B$2:$B$4",
        }
    )
    chart.set_title({"name": "Reference series"})
    chart.set_legend({"position": "bottom", "overlay": False})
    chart.set_y_axis({"num_format": "0"})
    chart.set_size({"width": 480, "height": 300})
    sheet.insert_chart("F2", chart, {"x_offset": 0, "y_offset": 0})
```

The checksum freezes the retained original input. Reproduction should match it
under the recorded tool version and settings; verify both bytes and semantics
before proposing any replacement. Never regenerate or update expectations from
a candidate application's save result.

## Remaining visual verification

No browser was run for this fixture-preparation task. OOXML placement/style
inspection establishes stored presentation semantics only. Live GridCraft chart
rendering, source-range outlines, visible values and headed/unattended profile
geometry remain unexecuted. There is no `visual/manifest.json` or baseline image
yet: measured crops, masks, thresholds and profile identities must be independently
reviewed and frozen during task 3.2 before acceptance runs. This fixture audit
does not establish browser readiness, persistence/reopen behavior, feature
delivery or financial-method assurance.
