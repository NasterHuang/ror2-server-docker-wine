# Building the compatibility staging

[English](building.en.md) · [简体中文](building.zh-CN.md) · [Deployment](deployment.en.md)

These are source-build notes for Steam build `25921972`, not a complete installer. The repository has the source and pinned inputs for the native FPTS overlay, but the complete V7 staging used in the test records is a local artifact. A fresh clone does not contain it.

You need Python 3.11+, the .NET 8 SDK (the recorded compiler was `8.0.426`), a clean owned game snapshot, and the complete PDB matching that exact UnityPlayer. Do not reuse offsets from a different Unity binary.

## Build the native overlay

Run from the repository root. Every output directory must be new. The PDB and game paths below are examples of private local inputs.

```sh
python3 tools/mods.py install --lock profiles/steam-25921972-source-overlay.experimental.lock.json --cache output/mod-cache --target output/rebuild-official --download
python3 Compatibility/FixPluginTypesSerialization/build.py --dotnet dotnet --output output/rebuild-fpts
python3 tools/unity_symbols.py --unity-player output/source-25921972/UnityPlayer.dll --pdb output/unity-symbols/UnityPlayer_Win64_player_mono_x64.complete.pdb --fpts-dll output/rebuild-official/BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/FixPluginTypesSerialization/FixPluginTypesSerialization.dll --config-out output/rebuild-fpts.cfg --audit-out output/rebuild-symbols.json
python3 tools/native_overlay.py --base output/rebuild-official --build output/rebuild-fpts --config profiles/native/steam-build-25921972.FPTS.cfg --output output/rebuild-native-overlay
```

The symbol tool audits the official DLL. Compare its generated configuration with the committed configuration before assembling the overlay. The committed configuration applies only to UnityPlayer SHA256 `fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105` and its recorded PDB identity. The overlay deliberately replaces the official FPTS DLL with a maintained source build and records that change.

**Stop here if you only have the native overlay.** It is one component of the server staging. It still needs a matching generated MMHOOK, the [ServerTools/Wwise component](../ServerTools/README.md), loader configuration, and reviewed release metadata. There is not yet one supported command that assembles all of those from a fresh clone. The official FPTS 1.0.4 binary alone crashed in the recorded environment; installing the official archive lock is not a substitute for this work.

## Extending an existing reviewed V7 base

If you already have a complete reviewed V7 mod staging and its release inventory, the later profiles can be assembled offline. The six-player step is:

```sh
python3 tools/approved_server6.py --base output/mods-server-v7 --lock profiles/approved-server-only-6.lock.json --cache output/mod-cache --output output/mods-server-approved-6-rebuilt
```

`output/mods-server-v7` is a private build artifact, not a directory created by cloning this repository. The cache must contain the exact official archives named by SHA256; the tool verifies the base and refuses a partial substitute. Rebuilding a base with different hashes requires a fresh audit, not editing the expected hashes just to make it pass.

The headless pillar-ping and Faster Everything steps have additional exact-input requirements. Their configuration and commands are in [the profile notes](../profiles/README.md), [pillar setup](mods-approval-20261018.md), and [Faster Everything setup](faster-everything.md). Those engineering records are currently in Chinese.

For the generic `runtime.py prepare` path, `mods/` may contain only `BepInEx/`, `winhttp.dll`, `doorstop_config.ini`, optional `.doorstop_version`, and `mods-lock.json`. Keep the assembly-stage root `release.json` outside that directory; runtime preparation creates its own inventory. Keep native compatibility metadata under `BepInEx/patchers/`. Do not copy just a handful of plugin DLLs or the entire game runtime into `mods/`.

Return to the [deployment guide](deployment.en.md) only when the complete staging has been reviewed. An assembled directory is still a test candidate; it needs a real server boot and client/gameplay checks.
