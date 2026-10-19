# Risk of Rain 2 Server — Docker/Wine Implementation

This project implements **one way to run a Risk of Rain 2 game server on Linux**: apply build-specific patches to a clean Windows game copy, route its startup and networking through the game's existing server code, and run that copy under Wine inside Docker.

English · [简体中文](README.zh-CN.md)

[![Checks](https://github.com/NasterHuang/ror2-server-docker-wine/actions/workflows/ci.yml/badge.svg)](https://github.com/NasterHuang/ror2-server-docker-wine/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

## How it works

The game simulation still runs in the original Windows executable and Unity assemblies. The project changes how that game copy starts and hosts a session:

1. **Patch a separate, verified game copy.** `RoR2Patcher` checks the clean `RoR2.dll` hash, method signatures, and IL locations before applying the reviewed manifest. The deferred-server profile skips the desktop Steam client initialization block, selects the game's existing dummy user manager, and defers real Steam game-server creation until the normal `host` path, after the game catalogs have loaded. Reviewed network calls use the server singleton.
2. **Run the Windows game headlessly on Linux.** Wine provides the Windows compatibility layer. The supervisor starts the game with `-batchmode -nographics` and supplies an Xvfb display for the runtime. Docker packages Wine and the tools, mounts the game source read-only, and keeps the prepared runtime, configuration, and Wine prefix in persistent storage.
3. **Handle the exact Unity/mod combination.** The modded configuration uses BepInEx and build-specific compatibility components. The maintained FPTS overlay and Wwise adapter address the native serialization and loading issues found in the recorded environment. Each component must match the reviewed game and dependency versions.
4. **Use the game's real server connection path.** The original build identity and Steam authentication checks remain in place. Players connect from the regular Steam game; this approach does not require them to install the server patches. FRP can optionally relay UDP traffic when direct access is unavailable; it does not implement the server itself.

```text
Clean Windows game copy → reviewed assembly patches + matching compatibility components
                        → Wine / headless Unity inside Docker on Linux
                        → game server ← Steam players (direct UDP or optional FRP relay)
```

This is a conversion of the game's startup and hosting path, not a reimplementation of its simulation or protocol. It can run on an x86 Linux server or ImmortalWrt router. The code builds on [albodin/RoR2Server](https://github.com/albodin/RoR2Server), with additional exact-build checks, compatibility work, and deployment tooling.

## Where things stand

**This is still an experimental server project.** The current records cover Steam build `25921972`. An unmodded diagnostic client has joined over FRP, passed real Steam authentication, and started the first stage on the server. That test used a headless client; it does not establish that normal graphical play or a full multiplayer session works reliably.

Two-player synchronization, more than four players, repeated stage changes, revival, and long sessions still need hands-on testing. The latest server-side mod settings also need their own gameplay checks. The [test record](docs/status.md) keeps the details, including failed attempts.

If you want to help test or work on a home-hosted server, there is useful code here. If you need a ready-made server you can deploy in one command, the project is not there yet.

## What's included

- A patcher that checks the exact game assembly before changing it. Game build identity and Steam authentication stay intact.
- A Docker/Wine runtime with startup deadlines, limited retries, file checks, and a previous-runtime rollback path.
- Pinned mod sources and local compatibility code for this game build. The current profile includes TooManyFriends, PillarRevive, and Faster Everything.
- ImmortalWrt firewall and boot helpers, plus an FRP template for a server behind NAT.
- Offline Python and synthetic IL checks, with Linux and Windows CI.

The repository contains source and configuration templates. You supply your own legally obtained game files and Steamworks support files. Game files, credentials, runtime archives, and mod binaries are not shipped here.

## Deploying a server

Start with the **[English deployment guide](docs/deployment.en.md)**. It covers the inputs you need, configuration, Docker startup, a storage-limited router setup, player connections, and rollback. There is a matching **[Chinese guide](docs/deployment.md)**.

```sh
git clone https://github.com/NasterHuang/ror2-server-docker-wine.git
cd ror2-server-docker-wine
cp .env.example .env
```

Before starting Docker, prepare the matching game snapshot, reviewed manifest, Steamworks DLLs, and complete mod staging described in the guide. Building the image alone does not provide those inputs. The mod staging still has manual build steps; [source build notes](docs/building.en.md) explain what is available and what remains unfinished.

Players use the normal Steam client. For a LAN connection, open the game console and substitute your private values:

```text
cl_password "YOUR_SERVER_PASSWORD";
connect "YOUR_LAN_HOST:27015";
```

FRP players use the relay's game port instead. See the deployment guide before opening public ports.

## Finding your way around

| Area | What to look for |
| --- | --- |
| [RoR2Patcher](RoR2Patcher/README.md) | Exact-build manifests, assembly transforms, and audit notes |
| [Compatibility](Compatibility/) | FPTS maintenance code and the headless PillarRevive adapter |
| [ServerTools](ServerTools/README.md) | Server status reporting and the Wwise compatibility component |
| [Mod profiles](profiles/README.md) | Archive locks, configuration, and assembly stages |
| [Deployment](docs/deployment.en.md) | Setup and day-to-day maintenance |
| [Network notes](docs/network-performance.md) | FRP, UDP, resource measurements, and synchronization testing |
| [Validation checklist](docs/validation.md) | What a proper multiplayer test needs to cover |

Some engineering notes are currently in Chinese. References to `output/` point to local test artifacts, not public downloads. Older client test packages are historical diagnostics; players do not need them to join.

## Development

Python 3.11+ and the .NET 8 SDK are enough to run the offline checks:

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

These use synthetic inputs rather than proprietary game assemblies. See [contributing](CONTRIBUTING.md) for patch-review and test expectations, and [security](SECURITY.md) before sharing logs.

For compatibility with existing deployments, internal `Rains.*` plugin identifiers, `/opt/ror2` paths, and the Compose project name `rains` are retained. The descriptive repository name does not change those runtime identities.

## Credits and license

Thanks to the original RoR2Server author and the mod authors whose work makes this experiment possible. This implementation retains [GPL-3.0](LICENSE); the vendored FPTS source retains its LGPL-3.0 license. See [third-party notices](THIRD_PARTY_NOTICES.md) for the source records. Risk of Rain 2, Steam, and Unity belong to their respective owners; this is an unofficial project.
