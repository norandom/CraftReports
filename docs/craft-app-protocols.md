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

## How this differs from Collabora and Microsoft 365

Comparison checked against the linked upstream documentation on 2026-10-14.
This compares the downloaded GridCraft browser release with Collabora Online and
Microsoft 365 for the web's external-storage integration.

| Concern | GridCraft web 0.6.1 | Collabora Online | Microsoft 365 for the web |
| --- | --- | --- | --- |
| Editing state | WASM application in the selected browser page | Server document engine with a browser client | Microsoft editor service with its browser experience |
| What you host | Static HTML/JS/WASM assets, as in this repository's nginx recipe | Collabora service plus integration with a document storage/access-control host | Your storage/WOPI host and embedding page; Microsoft supplies the web editor |
| File boundary | Browser file picker for Open; Save picker or download fallback | WOPI host supplies document access and persistence | WOPI host exposes file identity, metadata, content and updates |
| Main integration work | Prove control of the actual browser workbook and explicit save/reopen | Connect editor, WOPI host and browser, including session routing | Discovery, host page, tokens, WOPI operations and program requirements |

GridCraft's [release mode contract](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/main.rs)
describes browser file picking/downloads and the absence of native TCP control.
The [release-tagged browser implementation](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/web.rs)
attempts a native Save picker when available and otherwise uses a download
fallback; cancellation is not persistence. Verify the route actually exercised.
This is upstream behavior, not evidence that CraftReport has tested every file
operation. Collabora's [architecture and integration FAQ](https://www.collaboraonline.com/faqs/)
places document processing on the server and storage/access control with the
integrator. Its [official integration examples](https://github.com/CollaboraOnline/collabora-online-sdk-examples/blob/master/webapp/README.md)
show the browser, WOPI host and editor as separate participants.
Microsoft's [integration overview](https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/online/overview)
describes the corresponding service, storage and embedding boundaries.

Microsoft's external-storage integration is subject to the Cloud Storage Partner
Program; an ordinary Microsoft 365 subscription does not itself grant that
integration. Check the current program requirements before choosing it.
Collabora's [CODE Docker documentation](https://sdk.collaboraonline.com/25.04/CO-SDK-manual.pdf)
describes an editor-server container and allowed WOPI hosts. That is a different
deployment from serving GridCraft's static archive. Neither integration is
implemented or selected by CraftReport.

## State, storage and commands answer different questions

| Layer | Question it answers | What to verify |
| --- | --- | --- |
| Editor/session state | Which workbook is open, and where did this edit execute? | Page or engine identity and visible/observed content |
| WOPI storage integration | Which stored file can this editor read or update? | Stable file ID, version, permissions/token, applicable locks and saved bytes |
| Operation control through REST/MCP or an app API | Which action was requested against which target? | Typed request, admission, target effect and result/evidence readback |
| Artifact transfer | Did the chosen snapshot survive saving and reopening? | Exact output identity, actual bytes and reopened content |

WOPI does not define a universal stream of cell-edit deltas, a CraftReport
operation API, or a bridge to an arbitrary browser tab. Its file operations and
locks support an editor integration; the editor's own session/collaboration
protocol carries interactive editing. Microsoft's
[WOPI requirements](https://learn.microsoft.com/en-us/microsoft-365/cloud-storage-partner-program/online/wopi-requirements)
distinguish metadata/content reads from writes and locking needed for editing.

A JSON payload or an MCP success response alone cannot show which workbook
changed. For CraftReport, match producer snapshot, operation, app session and
output artifact explicitly. Static hosting leaves persistence and collaboration
as capabilities to verify separately; it does not turn nginx into a document
storage or collaboration service.

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
| CraftReport kernel REST/MCP facade | Python service and selected capability adapter | The stages supported by its checked result and evidence |

The 0.6.1 browser build does not expose the desktop TCP control bridge, as stated
in its [mode contract](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/main.rs).
A successful command against a headless MCP engine does not update or inspect a
browser workbook by implication. Hosting both on one machine or giving both the
same filename does not make their document state identical.

CraftReport's kernel exposes REST/MCP through shared typed operations and guards;
its installed verification uses synthetic providers. See the
[current readiness summary](index.md#current-readiness) for the reporting boundary.
MCP itself is a calling protocol; it neither requires AI nor establishes a
connection to an arbitrary open browser tab.

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
