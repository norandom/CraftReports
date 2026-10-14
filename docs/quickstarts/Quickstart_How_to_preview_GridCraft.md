# Quickstart: how to preview GridCraft

Open the official GridCraft 0.6.1 browser application and verify that its
spreadsheet responds to input. This preview evaluates the app's hosting and
rendering; CraftReport reporting integration remains pending.

## Before you start

You need a checkout, Linux or Debian WSL, Docker with a running daemon and
Compose, plus curl, unzip and sha256sum. Use a project-specific browser profile
or context. The existing development probe owns port 8871; the reusable setup
recipe owns a separate Compose project on 8872.

## Open the preview

1. Follow [prepare Linux or Debian WSL](../gridcraft-setup.md#prepare-linux-or-debian-wsl).
2. [Download and verify the release](../gridcraft-setup.md#download-and-verify-the-release).
   Continue only after the archive checksum reports `OK`.
3. [Configure and start the static container](../gridcraft-setup.md#configure-and-start-the-static-container).
   Wait for Compose startup to succeed, then open `http://localhost:8872/`.
   Substitute your selected port if you changed it.
4. Wait for the grid and ribbon to render. Click a visible cell, note its
   selection, and press ArrowDown. Check that the selection moves in that page.

## Verify the result

Retain a screenshot of the rendered app and the changed selection, with the
release/hash, Compose project, URL, browser and workbook identity. Inspect browser
console errors and failed asset requests. HTTP 200 alone does not prove rendering.

A native or headless MCP workbook is a separate session unless a verified bridge
connects it. This preview does not establish live reporting updates or saved XLSX
content. See [Craft app protocols](../craft-app-protocols.md).

## If it does not work

| Observation | Next action |
| --- | --- |
| Compose reports a port collision | Select an unused port; keep the existing probe on 8871 running |
| The page stays blank | Check asset failures, the mount root, WASM MIME type and graphics diagnostics in [setup](../gridcraft-setup.md#operate-and-upgrade-your-instance) |
| Linux curl works but the Windows browser cannot connect | Check published ports and [WSL address routing](../gridcraft-setup.md#understand-which-address-is-reachable) |

## Close or continue

Use the setup guide's [stop/start/down commands](../gridcraft-setup.md#operate-and-upgrade-your-instance)
for your owned Compose project. To evaluate the Python side next,
[verify the kernel](Quickstart_How_to_verify_the_kernel.md).
