# Run GridCraft in a browser without a Rust build

Download the official web archive and serve it with Docker Compose. The archive
contains the compiled spreadsheet application, including an approximately 18 MB
WebAssembly file, JavaScript loader and HTML page. nginx serves those files;
the spreadsheet engine runs in the browser. No local Rust toolchain is needed.

This guide pins GridCraft 0.6.1, the latest official release checked on
2026-10-14. It is an app-hosting recipe, separate from the unfinished CraftReport
service. See the [official release](https://github.com/storytold/gridcraft/releases/tag/v0.6.1)
and the `HOSTING.md` included in its archive.

## Prepare Linux or Debian WSL

You need a running Docker daemon with Compose, plus `curl`, `unzip` and
`sha256sum`. The current workstation uses Docker inside Debian WSL. From
PowerShell, enter it with:

```powershell
wsl.exe -d Debian
```

Run the remaining shell commands in Linux. For this workstation, the checkout is
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
  curl --fail --location --output gridcraft-web-0.6.1.zip \
    https://github.com/storytold/gridcraft/releases/download/v0.6.1/gridcraft-web-0.6.1.zip
  printf '%s  %s\n' \
    86048ba175689ff852c141d6115e5491f0856f891300c3e1f91274b9c2709a42 \
    gridcraft-web-0.6.1.zip | sha256sum --check --strict
  unzip -n gridcraft-web-0.6.1.zip -d web
  test -f web/gridcraft-web-0.6.1/index.html
)
```

Continue only after this prints `gridcraft-web-0.6.1.zip: OK` and exits
successfully. The digest identifies the exact release archive used by the local
probe. Preserve the release's license files with the extracted application.

## Configure and start the static container

The checked-in [Compose example](deployment/gridcraft/compose.yaml) mounts the
release read-only and pins nginx by image digest. The adjacent
[nginx configuration](deployment/gridcraft/nginx.conf) provides the WASM MIME
type and asset caching. Both files are documentation examples; downloaded app
files remain outside the source tree.

The existing development probe owns port 8871. This recipe uses 8872 for a
separate instance; select another unused port before starting if needed.
From the checkout root, copy the configuration and set the Linux absolute path:

```sh
cp docs/deployment/gridcraft/compose.yaml artifacts/gridcraft-local/compose.yaml
cp docs/deployment/gridcraft/nginx.conf artifacts/gridcraft-local/nginx.conf
cd artifacts/gridcraft-local
printf 'CRAFT_WEB_ROOT=%s\nCRAFT_HTTP_BIND=0.0.0.0\nCRAFT_HTTP_PORT=8872\n' \
  "$PWD/web/gridcraft-web-0.6.1" > .env
(
  set -e
  docker compose -p craftreport-gridcraft-local config --quiet
  docker compose -p craftreport-gridcraft-local up -d
  docker compose -p craftreport-gridcraft-local ps
  curl --fail --head http://localhost:8872/
)
```

Keep the Compose project name unique. The subshell stops on a failed startup,
so a response from another service cannot mask a port collision. Leave the
existing `craftreport-gridcraft-probe` project on 8871 running.

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

The [0.6.1 browser mode contract](https://github.com/storytold/gridcraft/blob/v0.6.1/apps/gridcraft-web/src/main.rs)
specifies no desktop TCP control bridge. A native or headless MCP
session owns a different workbook unless a separately verified bridge connects
it. See [Craft app protocols](craft-app-protocols.md) before implementing an
adapter.

## Operate and upgrade your instance

Run these commands in your `artifacts/gridcraft-local` directory:

```sh
docker compose -p craftreport-gridcraft-local logs --tail=100 web
docker compose -p craftreport-gridcraft-local stop
docker compose -p craftreport-gridcraft-local start
# Remove only this project's containers and network when finished:
docker compose -p craftreport-gridcraft-local down
```

The bind-mounted app files remain on disk. The container serves the application;
it is not a workbook storage service. Treat browser state and downloaded files
according to the app's actual save behavior and verify recovery before relying
on it.

For an upgrade, select the latest official release, record its asset hash and
extract into a new version directory. Read that archive's hosting notes, point
`CRAFT_WEB_ROOT` at it, and recreate this project's service with
`docker compose -p craftreport-gridcraft-local up -d --force-recreate`. Repeat
browser, file and integration checks relevant to your use case. Retain the old
version and configuration until those checks pass so the same command can
restore the previous directory. Review the nginx image pin separately.

If the page stays blank, inspect browser errors and failed asset requests first.
Confirm the mounted directory contains `index.html` directly, `.wasm` is served
as `application/wasm`, and the browser has a usable graphics backend. If Linux
`curl` works but Windows does not, check port publication and WSL networking
before changing the app. No successful HTTP request proves browser rendering.
