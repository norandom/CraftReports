# Craft apps, browser sessions and WOPI

GridCraft's web release can run without WOPI because it supplies its own
spreadsheet application and engine, compiled to WebAssembly. A static web server
delivers that application to the browser. WOPI is an integration protocol for a
document host and an editor; it is not a prerequisite for executing a browser
spreadsheet.

This distinction matters when choosing the next integration step. Serving
GridCraft gives a user an editor. Connecting a Python reporting operation to the
workbook in that editor still requires a supported control path with identified
sessions and verified effects.

## What WOPI connects

In Microsoft's integration, a storage provider implements HTTP endpoints that
Microsoft 365 for the web uses to inspect, fetch and update files. The storage
service is the WOPI host; the editor is the WOPI client. Operations cover file
metadata/content and editing coordination such as locks. Discovery tells the
host which editor actions and URLs are available. See Microsoft's
[overview](https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/online/overview)
and [WOPI API reference](https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/rest/).

A file lock coordinates access to a stored file. It does not, by itself, provide
real-time multiuser collaboration; that also needs editor/session behavior and
its own supported integration.

That is useful when the chosen editor expects WOPI to access externally stored
documents. Choosing Microsoft 365 for the web would introduce its own documented
integration and program requirements. Serving GridCraft's independent app
archive does not invoke Microsoft 365 for the web.

## What the GridCraft release contains

The official [GridCraft 0.6.1 release](https://github.com/storytold/gridcraft/releases/tag/v0.6.1)
includes a web archive with HTML, JavaScript and the compiled WASM application.
The archive's `HOSTING.md` describes static hosting and browser downloads.
Its [browser entry point](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/web.rs)
starts the app in the browser, rather than embedding Microsoft Excel. An iframe
can embed that page, but embedding does not establish a workbook command API.

This supports a reusable acquisition pattern: select an official prebuilt web
asset, verify its checksum, serve its files, then test that app's actual browser
behavior. Other Craft apps need their own release and capability checks. This
repository has not established that every Craft app has the same web package,
protocols or supported operations.

## Keep the execution modes separate

| Surface | Where the workbook and execution live | What a successful call proves |
| --- | --- | --- |
| GridCraft web/WASM | The selected browser page/session | Only the action and effect verified in that page |
| GridCraft desktop | The selected native process/document | Only the native session reached by its supported control path |
| Headless engine/MCP | The engine session owned by that server | Only that server's selected document and operation |
| Planned CraftReport REST/MCP facade | Python service and selected capability adapter | The stages supported by its checked result and evidence |

The 0.6.1 browser build does not expose the desktop TCP control bridge, as stated
in its [mode contract](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/main.rs).
A successful command against a headless MCP engine does not update or inspect a
browser workbook by implication. Hosting both on one machine or giving both the
same filename does not make their document state identical.

CraftReport's REST/MCP surfaces are still under implementation. The intended
contract makes both ordinary software callers and optional AI callers use the
same typed operations and guards. MCP itself is a calling protocol; it neither
requires AI nor establishes a connection to an arbitrary open browser tab.

## Choose integration by the promised effect

For a user opening and editing GridCraft, use the
[static hosting guide](gridcraft-setup.md). For automated browser behavior,
exercise the real page through a verified UI interaction path and check the
result in that session. Canvas rendering can require keyboard/pointer input and
visual inspection rather than ordinary DOM field selectors.

For native automation or headless file processing, select the release's actual
supported interface and record the process, engine and document identities.
When transferring a file between modes, treat export, import and reopen as
explicit operations with their own evidence. File transfer does not create a
live shared session.

A future live browser adapter must identify a supported bridge, bind it to the
intended page/workbook, and prove changes there. Adding a WOPI host alone would
not supply that missing bridge: the editor would also need compatible WOPI
client behavior. WOPI becomes relevant when a selected integration requires it,
not merely because a workbook is opened in a browser.
