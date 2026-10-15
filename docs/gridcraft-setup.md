# Run GridCraft in a browser without a Rust build

Download the official web archive and serve it with Docker Compose. The archive
contains the compiled spreadsheet application, including its WebAssembly engine,
JavaScript loader and HTML page. nginx serves those files;
the spreadsheet engine runs in the browser. No local Rust toolchain is needed.

This guide pins GridCraft 0.7.0, the latest official release checked on
2026-10-15. It is an app-hosting recipe, separate from the unfinished CraftReport
service. See the [official release](https://github.com/storytold/gridcraft/releases/tag/v0.7.0)
and the `HOSTING.md` included in its archive.

## Prepare Linux or Debian WSL

You need a running Docker daemon with Compose, plus `curl`, `unzip` and
`sha256sum`. The current workstation uses Docker inside Debian WSL. From
PowerShell, enter it with:

```powershell
wsl.exe -d Debian
```

Run the preparation shell commands in Linux. For this workstation, the checkout is
`/mnt/d/Source/GridDash`; on another machine, use its checkout path. A native Linux
host uses the same commands after that path change.

```sh
cd /mnt/d/Source/GridDash
docker version
docker compose version
command -v curl unzip sha256sum
```

The daemon must be accessible to your Linux user. These instructions assume that
Docker is already installed and do not change daemon permissions or firewall
rules.

## Download and verify the release

Use an owned directory under the ignored `artifacts/` tree. Run this block in
Bash; a failed download or checksum stops the subshell before extraction.

```bash
(
  set -euo pipefail
  mkdir -p artifacts/gridcraft-local
  cd artifacts/gridcraft-local
  curl --fail --location --output gridcraft-web-0.7.0.zip \
    https://github.com/storytold/gridcraft/releases/download/v0.7.0/gridcraft-web-0.7.0.zip
  printf '%s  %s\n' \
    ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27 \
    gridcraft-web-0.7.0.zip | sha256sum --check --strict
  unzip -n gridcraft-web-0.7.0.zip -d web
  test -f web/gridcraft-web-0.7.0/index.html
)
```

Continue only after this prints `gridcraft-web-0.7.0.zip: OK` and exits
successfully. The digest matches the official release asset and the locally
cached archive. Preserve the release's license files with the extracted application.

## Configure and start the static container

The checked-in [Compose example](deployment/gridcraft/compose.yaml) mounts the
release read-only and pins nginx by image digest. The adjacent
[nginx configuration](deployment/gridcraft/nginx.conf) provides the WASM MIME
type and asset caching. Both files are documentation examples; downloaded app
files remain outside the source tree.

This Compose file is a reusable static-hosting recipe, not the running probe's
configuration or a self-contained GridCraft image. `CRAFT_WEB_ROOT` supplies the
extracted application, including its compiled WASM engine, through the volume
mounted at `/usr/share/nginx/html`. Starting the YAML without the downloaded
bundle and that variable does not install the app. The running probe has its
own configuration under `artifacts/gridcraft-deployment-probe/` and uses port
8871; the documented recipe defaults to a separate instance on 8872. Neither
configuration starts a Rust backend daemon or a CraftReport Python service.

The existing development probe owns port 8871. This recipe uses 8872 for a
separate instance; select another unused port before starting if needed.
From the checkout root, copy the configuration and set the Linux absolute path:

```sh
cp docs/deployment/gridcraft/compose.yaml artifacts/gridcraft-local/compose.yaml
cp docs/deployment/gridcraft/nginx.conf artifacts/gridcraft-local/nginx.conf
cd artifacts/gridcraft-local
printf 'CRAFT_WEB_ROOT=%s\nCRAFT_HTTP_BIND=0.0.0.0\nCRAFT_HTTP_PORT=8872\n' \
  "$PWD/web/gridcraft-web-0.7.0" > .env
docker compose -p craftreport-gridcraft-local config --quiet
```

Continue only if configuration validation succeeds. On Windows with Debian WSL,
run this in PowerShell and leave it attached throughout browser use. Adjust the
checkout path if yours differs; `--cd` selects the directory containing the
copied Compose file, nginx configuration and `.env`:

```powershell
wsl.exe -d Debian --cd /mnt/d/Source/GridDash/artifacts/gridcraft-local -- docker compose -p craftreport-gridcraft-local up
```

Keep that terminal open. Docker's systemd service alone does not keep WSL alive;
after the last WSL client exits, the host can shut down and the browser's next
request can fail. See [Microsoft's WSL service lifetime note](https://learn.microsoft.com/en-us/windows/wsl/systemd#how-does-enabling-systemd-affect-wsl-architecture).
Ctrl+C stops the attached Compose service. On native Linux, start normally from
`artifacts/gridcraft-local` with `docker compose -p craftreport-gridcraft-local up -d`.

In another Linux/WSL terminal, enter the same `artifacts/gridcraft-local`
directory and check startup:

```sh
docker compose -p craftreport-gridcraft-local ps
curl --fail --head http://localhost:8872/
```

Check Compose errors and the project's published port before continuing, so
another service cannot mask a port collision. Keep the project name unique and
leave the existing `craftreport-gridcraft-probe` project on 8871 running.

Open `http://localhost:8872/` in the Windows browser for WSL, or the Linux host's
browser for native Linux. Substitute the selected port everywhere. An HTTP 200
checks delivery; wait for the grid and ribbon to render before calling the app
usable.

## Understand which address is reachable

`0.0.0.0` is a bind address, not a browser destination. The default publishes the
container on all Linux host interfaces. For native Linux access from another
machine, use `http://<linux-host-address>:8872/` when that network path is allowed.
For access limited to the Linux host, set `CRAFT_HTTP_BIND=127.0.0.1`.

Windows can normally reach a WSL-hosted app through `localhost`. WSL's default
NAT and mirrored networking have different LAN behavior; a Linux all-interface
bind alone does not prove that another LAN machine can reach Windows and WSL.
Use the actual Windows/WSL networking mode when configuring remote access.
See [Microsoft's WSL networking guide](https://learn.microsoft.com/en-us/windows/wsl/networking).

The example provides plain HTTP for local use and no access control. For a
shared deployment, configure the site's HTTPS and access policy at its ingress.
GridCraft's bundled hosting guide specifies a secure context for WebGPU and
clipboard support; ordinary remote HTTP can fall back to WebGL2. No special
cross-origin isolation headers are required by this release.

## Verify the app and retain evidence

Use a separate browser profile or automation context for this project. Record
release version/hash, container image, Compose project, URL, browser version and
workbook identity. Check a real input action, capture the result and retain
console/network diagnostics. If testing export, inspect the actual download and
reopen it; a screenshot alone cannot establish saved content.

Observed on 2026-10-14: the owned Debian WSL deployment was reachable from
Windows at `http://localhost:8871/`. An isolated Playwright run in Chromium
153.0.8010.12 rendered the Quarterly Sales Dashboard, its table and charts,
recorded an ArrowDown input, and retained screenshots and a flushed video. The
sample URL was `http://localhost:8871/?sample=sales`.
The WASM response was HTTP 200 with `application/wasm`. No page errors or failed
requests were reported. Renderer fallback and other browser warnings were
retained in the diagnostics. This was a rendering/input smoke check; it did not
verify live MCP control, save/export, reopen, or CraftReport integration.
The probe evidence is local under `artifacts/gridcraft-deployment-probe/` and is
not distributed with the repository.

The [0.7.0 browser mode contract](https://github.com/storytold/gridcraft/blob/v0.7.0/apps/gridcraft-web/src/main.rs)
specifies no desktop TCP control bridge. A native or headless MCP
session owns a different workbook unless a separately verified bridge connects
it. See [Craft app protocols](craft-app-protocols.md) before implementing an
adapter.

## Use this deployment for end-to-end testing

The commands above prepare an app target. A repeatable CraftReport browser
acceptance suite remains a separate
[roadmap scope](roadmap.md#delivery-sequence-and-gates). The existing probe is a
rendering/input smoke check, not an implemented full reporting test runner.

For a browser journey, use this run structure with the selected Playwright
environment. Keep the test fixture synthetic and the browser context separate
from everyday browsing.

| Stage | Action and evidence |
| --- | --- |
| Identify | Record archive checksum, container image, Compose project, origin, browser version, fixture and workbook identity in the run directory |
| Observe | Enable video and download capture; collect page errors, failed requests and console messages before navigating |
| Interact | Wait for the actual grid, perform the intended keyboard/pointer or supported UI action, then assert the content changed in that page |
| Persist | Capture the real save/export download; inspect its bytes/content and reopen it in the intended app or reader |
| Reconcile | Compare the reopened values and report version with the fixture and, once connected, the producer snapshot and facade receipt |
| Close | Close the owned browser context to flush video; retain screenshots and diagnostics and stop only the Compose project owned by the run |

For the planned live report, also test refresh during export and the specified
pause/resume and rejected-update behavior. Treat unavailable save/control paths
as unresolved capability findings. A headless MCP result cannot substitute for
the browser action. The [protocol comparison](craft-app-protocols.md) explains
where GridCraft, Collabora and Microsoft 365 keep editing and stored-file state.

A test run's browser address must be reachable from the machine running the
browser. Windows `localhost:8872`, Linux container service names and remote
hostnames are not interchangeable. Preserve the existing probe on port 8871;
parallel runs need distinct project names, ports, contexts and artifact paths.

## Reuse the pattern for another Craft app

Before adapting the Compose example, verify that the chosen app actually ships
an official prebuilt web archive. Record its release URL, asset checksum,
extraction root, entry page, WASM/assets, hosting requirements and supported
open/save/control behavior. Change the mount, project name and port for that
app, then repeat rendering, interaction and artifact checks.

The GridCraft manifest and observed behavior do not establish those properties
for WordCraft, DeckCraft or another app. Activate each integration through its
bounded scope before adding reporting adapters.

## Operate and upgrade your instance

Run these commands in your `artifacts/gridcraft-local` directory, using another
Linux/WSL terminal while Compose is attached:

```sh
docker compose -p craftreport-gridcraft-local logs --tail=100 web
docker compose -p craftreport-gridcraft-local stop
# Remove only this project's containers and network when finished:
docker compose -p craftreport-gridcraft-local down
```

To restart, use the platform-specific startup command above. On WSL, retain the
attached client again for the whole browser session.

The bind-mounted app files remain on disk. The container serves the application;
it is not a workbook storage service. Treat browser state and downloaded files
according to the app's actual save behavior and verify recovery before relying
on it.

For an upgrade, select the latest official release, record its asset hash and
extract into a new version directory. Read that archive's hosting notes, point
`CRAFT_WEB_ROOT` at it, and recreate this project's service with
`docker compose -p craftreport-gridcraft-local up --force-recreate` from the same
Linux/WSL directory. Keep it attached on WSL; native Linux can add `-d`. Repeat
browser, file and integration checks relevant to your use case. Retain the old
version and configuration until those checks pass so the same command can
restore the previous directory. Review the nginx image pin separately.

If the page stays blank, inspect browser errors and failed asset requests first.
Confirm the mounted directory contains `index.html` directly, `.wasm` is served
as `application/wasm`, and the browser has a usable graphics backend. If Linux
`curl` works but Windows does not, check port publication and WSL networking
before changing the app. No successful HTTP request proves browser rendering.

If an already loaded page still edits but reload or a fresh browser context
reports `ERR_CONNECTION_REFUSED`, check `wsl.exe --list --running` in PowerShell
before starting another WSL command. If Debian stopped, rerun the attached WSL
startup command and repeat the port and HTTP checks, then reload. The loaded
WASM app can keep working after its HTTP host has gone away. If Debian is still
running, inspect this project's status/logs and port routing instead.
