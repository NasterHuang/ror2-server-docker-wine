# Rains.TrialHeadlessFix

Server-only BepInEx plugin for DLC4 "Trials of N'kuhana" on a dedicated server
(`NetworkServer.active && !NetworkServer.localClientActive`).

## Problem

The UNet-weaver generated SyncVar setters on `RoR2.TrialController`
(`NetworkvariantIndex`, `NetworkhasTrialStarted`, `Network_trialControllerState`)
only invoke their hooks on the server when `NetworkServer.localClientActive`.
`TrialController` relies on those hooks for server logic (scene preparation,
`onTrialStartedGlobal`, `QuestStarter.BeginQuestServer` / 210 s shared timer,
inventory restore and success/failure). On a dedicated server none of them run,
so after leaving the start volume no objective or countdown appears.
Inventory safekeeping still happens because `OnStartServer` calls
`SafekeepAllInventories` directly.

## What it does

1. Transpiles only those three setters so the hook gate becomes
   "server active" instead of "local client active". Listen-host and pure
   client behaviour are unchanged. IL is verified at startup (exactly one gate
   per setter).
2. Prefix on `ContagiousItemManager.ProcessPendingChanges` drops pending entries
   whose `Inventory` was destroyed (logs `[contagion] removed`).
3. Log-only `[trial]` diagnostics (variant prepared, trial started, state
   changes, quest creation, countdown start, Hallowed Potential spawn).

The plugin checks SHA256 of the game/network assemblies and disables itself
entirely on mismatch (pinned to Steam build 25921972 as deployed).

## Build

```sh
dotnet build TrialHeadlessFix.csproj -c Release -p:Live=<path to data/runtime>
```

References are the exact DLLs from the deployed runtime. Deployed 0.1.0 DLL
SHA256 `d43ef6f894bed5a225ebe4c12363d451f1f00ff6be46e90e5e7dd0da9c0aaba7`
(built from this source; a rebuild from a different directory yields a
different hash because of embedded paths).

## Deploy / rollback

`deploy/` holds the scripts used on the router (`backup.sh`, `apply.sh`,
`rollback.sh`, `common.sh`). The plugin must also be listed in
`data/runtime/release.json` `modsInventory`, otherwise `verify_release`
refuses to launch. Rollback: stop the container, remove
`BepInEx/plugins/Rains.TrialHeadlessFix`, restore the previous
`release.json`, start the container.

Status: deployed 2026-11-14, awaiting in-game verification.
