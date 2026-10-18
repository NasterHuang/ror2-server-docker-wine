# RainHost

**A home for your Risk of Rain 2 server.**

English · [简体中文](README.zh-CN.md)

[![Checks](https://github.com/NasterHuang/ror2-rainhost/actions/workflows/ci.yml/badge.svg)](https://github.com/NasterHuang/ror2-rainhost/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

RainHost is a project for running a Risk of Rain 2 server on an x86 Linux machine, including a small home server or an ImmortalWrt router. The server runs under Wine in Docker; friends join from the regular Steam game without installing a separate client pack.

The idea is simple: let the server stay on while the gaming PC is off. Most of the work here goes into making that practical—starting the game without a desktop Steam client, keeping game files and mods in sync, and making failures easier to diagnose.

This started from [albodin/RoR2Server](https://github.com/albodin/RoR2Server). RainHost keeps that history and adds build-specific patches, maintained compatibility code, pinned mod profiles, and deployment tools for ImmortalWrt.

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
git clone https://github.com/NasterHuang/ror2-rainhost.git
cd ror2-rainhost
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

## Working on RainHost

Python 3.11+ and the .NET 8 SDK are enough to run the offline checks:

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

These use synthetic inputs rather than proprietary game assemblies. See [contributing](CONTRIBUTING.md) for patch-review and test expectations, and [security](SECURITY.md) before sharing logs.

RainHost was previously published as `rains`. Internal `Rains.*` plugin identifiers, `/opt/ror2` paths, and the Compose project name `rains` are retained so a documentation rename does not disrupt existing deployments.

## Credits and license

Thanks to the original RoR2Server author and the mod authors whose work makes this experiment possible. RainHost retains [GPL-3.0](LICENSE); the vendored FPTS source retains its LGPL-3.0 license. See [third-party notices](THIRD_PARTY_NOTICES.md) for the source records. Risk of Rain 2, Steam, and Unity belong to their respective owners; this is an unofficial project.
