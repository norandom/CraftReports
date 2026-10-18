# GridCraft capability budget calibration amendment

Status: approved by the project owner on 2026-10-18 (interactive decision during
task 9 implementation). This is a bounded numeric limit, not a waiver.

## Decision

Raise only the `gridcraft` aggregate production source limit from 1,500 to 2,000
logical lines for its already approved first-release responsibilities. Function
50, module 300 and McCabe 10 limits, every other capability limit, ownership,
release scope and acceptance requirements remain unchanged. No additional
operations, export support or generic framework are authorized by this change.

## Evidence

| GridCraft responsibility | LLOC basis |
| --- | ---: |
| Accepted tasks 1-8 (values, codecs, facts, browser, workbook, providers, artifacts, interactions) | 1,337 measured at HEAD, strict-typed |
| Task 9 operations, runtime integration and capability factory | ~315 measured |
| Task 10+ user-facing control-panel host glue, freshness and lifecycle wiring | 150-300 estimated |
| Total before deletions | 1,800-1,950 planning range |

Fitting task 9 under 1,500 required compressing accepted code (dynamic wire
shapes, untyped collections). That compression broke the mandatory strict
Pyright gate (~95 errors) and reduced readability while leaving no headroom for
the user-facing control panel. Repeated compression would delay the first usable
report workflow without demonstrating a complete, typed fit.

## Conditions

- Accepted task 1-8 modules are restored to their typed, reviewed form.
- Strict Pyright, Ruff lint/format and all existing local limits remain enforced.
- Estimates are not implemented source or a guarantee of final fit; exceeding
  2,000 requires a new reviewed amendment.
