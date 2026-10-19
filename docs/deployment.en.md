# Deploying the Risk of Rain 2 Docker/Wine server

English · [简体中文](deployment.md) · [Home](../README.md)

This guide covers the Docker/Wine deployment used by the project. The recorded game build is `25921972`; a newer Steam build needs a new audit. The last game checks were recorded on October 18, 2026. Publishing these instructions does not add new gameplay test results.

## Before you start

Use an **x86_64 Linux host** with Docker Engine and Docker Compose v2. The game is the Windows Steam version running under Wine. ImmortalWrt is an optional target, not a requirement. Build large artifacts on a separate x86 workstation if the server is also your router.

Allow enough space for the image, clean game, runtime, previous runtime, Wine prefix, and logs. For the normal two-copy workflow, plan for at least **20 GiB of free storage**, then check actual usage. A **4 GiB container memory limit** is a starting configuration, not a measured minimum. Leave CPU, RAM, and disk headroom for routing and other services.

You also need:

- A legally obtained, Steam-verified game copy matching the reviewed assembly.
- Genuine Windows x64 Steamworks SDK Redist support files from SteamCMD app `1007`: `steamclient64.dll`, `tier0_s64.dll`, and `vstdlib_s64.dll`; `steamwebrtc64.dll` is optional. Copy only these files into `config/steamworks/` and record their source and hashes. App `1007` supplies support files, not the game.
- The reviewed deferred-server manifest from this repository.
- For the tested modded path, a **complete, reviewed mod staging** containing the native FPTS overlay, matching generated MMHOOK, ServerTools/Wwise compatibility code, loader configuration, and the selected profile. See [source build notes](building.en.md).

**A fresh clone does not include that complete mod staging or a downloadable ready-to-run game image.** Some assembly steps remain manual. If you do not have a reviewed staging, complete that work before the startup section. `MODS_ENABLED=0` is a separate diagnostic experiment; it does not reproduce the tested modded setup.

## 1. Get the repository and create local configuration

Run the shell commands below on the Linux build/deployment host from the repository root, unless a step says otherwise.

```sh
git clone https://github.com/NasterHuang/ror2-server-docker-wine.git
cd ror2-server-docker-wine
cp .env.example .env
chmod 600 .env
mkdir -p config/steamworks mods data output
cp RoR2Patcher/manifests/steam-build-25921972.deferred-server.experimental.json config/patch-manifest.json
```

Keep `COMPOSE_PROJECT_NAME=rains` in `.env`. Existing router helpers expect that project name and `rains-ror2-server-1`; the checkout folder can still be named `ror2-server-docker-wine`. The rename does not require moving `/opt/ror2` or changing plugin identifiers.

## 2. Export and check the game

Finish Steam's update and file verification first. On the Windows machine that owns the game, use Python 3.11+ to export a clean copy. Replace the example Steam library path with your own; the target directory must not already exist.

```powershell
python tools/snapshot.py --game 'D:\SteamLibrary\steamapps\common\Risk of Rain 2' --target output/source-25921972 --steam-manifest 'D:\SteamLibrary\steamapps\appmanifest_632360.acf'
```

The exporter leaves the installed client untouched and excludes root-level old loaders. Transfer the **contents** of the exported snapshot into `game/` on the Linux host. `game/Risk of Rain 2.exe` should exist directly, not under a second nested directory.

```sh
sha256sum 'game/Risk of Rain 2_Data/Managed/RoR2.dll'
dotnet run --project RoR2Patcher -- --inspect --input 'game/Risk of Rain 2_Data/Managed/RoR2.dll' --report output/game-audit.json
```

The committed manifest expects clean DLL SHA256:

```text
48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c
```

If it differs, stop and audit that game build. Changing the expected hash alone does not update patch offsets or make a new build compatible. The early `experimental`, `server-bootstrap`, and `server-networking` manifests are retained for research; use the reviewed **deferred-server** selection for this workflow.

## 3. Put the remaining inputs in place

The directory layout should be:

```text
ror2-server-docker-wine/
  .env
  game/                         # clean Windows game snapshot
  config/
    patch-manifest.json
    steamworks/                 # the three required support DLLs
  mods/
    BepInEx/                    # core, patchers, plugins, config, provenance
    winhttp.dll
    doorstop_config.ini
    mods-lock.json
  data/                         # writable by the container user
```

The optional `.doorstop_version` file is also allowed in `mods/`. Keep the mod-assembly root `release.json` outside `mods/`; preparation writes a runtime release inventory of its own. The clean source, mod staging, support files, and writable data directory must be separate, non-overlapping trees.

Include `profiles/server-config/BepInEx.GUI.cfg` in the staging's `BepInEx/config/` before the first preparation. Once `data/bepinex-config/` exists, it is the persistent configuration: changing a staging default does not overwrite it. Stop the server before updating persistent settings.

Edit `.env` with your chosen server name and a private password. After reviewing the exact-build audit, the full modded profile uses these settings:

```dotenv
COMPOSE_PROJECT_NAME=rains
SERVER_MODE=experimental
ACK_EXPERIMENTAL=1
EXPECTED_GAME_SHA256=48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c
MODS_ENABLED=1
RAINS_SERVER_TOOLS=1
RAINS_RESTORE_CLIENT_WWISE=1
MAX_PLAYERS=6
MEMORY_LIMIT=4g
MIN_FREE_MB=1024
STARTUP_TIMEOUT_SECONDS=600
```

Set `MAX_PLAYERS=6` only when the matching six-player profile is installed; otherwise keep the profile's supported count. The Wwise switch requires the exact reviewed compatibility component. Do not enable either plugin switch just to silence missing-component errors. Set `SERVER_PASSWORD` separately in your private `.env`; the `change-me` example is not a deployment password. Passwords and hostnames cannot contain quotes, backslashes, semicolons, or newlines.

The default process UID/GID is `1000:1000`. On a new dedicated data directory, give that account write access (`sudo chown -R 1000:1000 data`). If using another UID/GID, set `PUID` and `PGID` and grant matching ownership. Do not make the game source writable to the container.

## 4. Build and start

Keep the host firewall limited to your LAN for the first test. Compose publishes the three UDP ports on the host; it does not restrict them to LAN clients.

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f --tail=200
```

The normal startup prepares a separate runtime, validates inputs, applies the reviewed patch, retains the previous runtime, and launches Wine. On Linux, plugin configuration is kept in `data/bepinex-config/`.

To check it:

```sh
docker compose ps
docker compose exec ror2-server python3 /opt/ror2/tools/runtime.py health
docker compose exec ror2-server python3 /opt/ror2/tools/runtime.py query --host 127.0.0.1 --port 27016
```

Use your configured query port if it differs. With ServerTools enabled, inspect fresh `data/status/game.json` samples for loading, host, and actual Steam login state. `boot.json`, an open UDP port, or Docker's `healthy` label alone does not prove that a client can play.

Startup has a 600-second deadline by default. Failed processes have at most three automatic retries. An `unhealthy` status by itself does **not** make Docker restart the container.

## 5. A router with limited storage

Prepare on a separate x86 Linux build host or Linux VM with a filesystem that preserves symlinks. Use the same reviewed inputs and `.env` as above, then build the image and prepare the data without starting a game:

```sh
docker compose build
docker compose run --rm --no-deps ror2-server prepare
docker save -o output/ror2-server-image.tar ror2-local:experimental
tar -cpf output/ror2-server-data.tar -C data runtime bepinex-config
sha256sum output/ror2-server-image.tar output/ror2-server-data.tar > output/ror2-server-transfer.sha256
```

Replace `ror2-local:experimental` if you set a different `ROR2_IMAGE`. This archive command assumes the modded preparation created `bepinex-config/`. Copy both archives and their checksums to the router privately, verify the hashes, then load the image with `docker load -i`. Keep the clean source and a known-good rollback copy on the workstation.

For a **new** deployment at `/opt/ror2`, place the Compose files, tools, profiles, and private `.env` there. Create `game/`, `config/`, `mods/`, and `data/`; extract the verified data archive into `data/`, preserving symlinks and ownership. Put the exact config/support inputs in their normal paths if you want to prepare there later. Never extract an archive over a live or partially transferred runtime.

```sh
cd /opt/ror2
docker compose -f docker-compose.yml -f compose.router.yml config --quiet
docker compose -f docker-compose.yml -f compose.router.yml up -d
```

This override runs `launch` against the prepared release instead of rebuilding the game on the router. It still checks the release before Wine starts. Keep at least the configured 1 GiB disk reserve after accounting for the image and Wine prefix. Local instant rollback is unavailable if the previous runtime only exists on your workstation.

The ImmortalWrt boot scripts keep the existing `rains` identity. Before installing them, check that the named paths and container belong to this deployment. Copy `tools/immortalwrt-boot-start.sh` to `/opt/ror2/deployment/`, install `tools/immortalwrt-ror2.init` as `/etc/init.d/rains-ror2`, make both executable, and run the script with `--check`. Then enable/start the init service. It starts an existing container; it does not create one or guarantee game readiness. Full host reboot and power-loss recovery remain untested in the published record.

## 6. Networking and player connections

| Purpose | Host/container UDP port | Example FRP public port |
| --- | --- | --- |
| Game | 27015 | 28015 |
| A2S query | 27016 | 28016 |
| Steam server | 27017 | 28017 |

The Compose bridge is `br-ror2`. ImmortalWrt/fw4 may require a project-specific zone. Inspect `sh tools/immortalwrt-firewall.sh status` before using its `apply` action: it permits WAN access to all three configured ports. The [firewall and recovery notes](deployment-notes.zh-CN.md) describe its ownership checks and limits. Do not change unrelated router zones to make a test pass.

For FRP, start from `profiles/frpc.example.toml`, supply your private relay address/token, and use the router's reachable LAN IP as the local target. The recorded host setup uses that address rather than `127.0.0.1`. Verify both the relay firewall and its UDP mappings. [Network notes](network-performance.md) cover the existing procd service and source lock; a shared frps must not be overwritten or restarted for this project.

Players launch the regular Steam game with a compatible build and crossplay disabled. Open the console with `Ctrl + Alt + backtick` and substitute the private values:

```text
cl_password "YOUR_SERVER_PASSWORD";
connect "YOUR_LAN_HOST:27015";
```

For the example FRP layout, use `connect "YOUR_PUBLIC_HOST:28015";`. The query may still advertise game port `27015`, so use the explicit external port rather than relying on the Steam browser to choose it.

Confirm real authentication, then test movement, damage, pickups, another player, stage changes, death/revival, and a longer run. The [validation checklist](validation.md) separates those checks. The October 18 test established single-client authentication and server-side stage startup, not complete graphical multiplayer play.

## Maintenance and rollback

Use the same Compose file selection for `stop`, `up`, and logs. On a router, that means both files.

1. Stop this server and save configuration, logs, `release.json`, `patch-report.json`, and the mod/source records to private storage.
2. Build updates separately. Review new game hashes and Unity offsets before preparing another release; do not automatically update mods at boot.
3. Verify the transfer completely before replacing the stopped deployment. Keep persistent configuration consistent with the selected profile.
4. If an update fails, stop the server and restore the last complete, reviewed runtime **and its matching configuration**. The normal preparation path retains one `data/previous`; do not swap it while the process is running. On a single-copy router, restore the workstation backup.

The native overlay, release inventories, and Steamworks support files are checked before launch. Resolve the mismatch at its source instead of editing inventories to make validation pass. Image tags can move; record the built image ID/digest, package versions, and game/mod hashes with your own release notes.

Keep `.env`, FRP tokens, SSH credentials, connection details, and raw logs out of Git. The [security notes](../SECURITY.md) cover reporting. Detailed historical deployment observations remain in [the engineering record](deployment-notes.zh-CN.md).
