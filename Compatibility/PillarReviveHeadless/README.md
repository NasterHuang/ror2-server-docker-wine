# PillarRevive headless automatic ping compatibility

This optional server plugin enables PillarRevive 1.1.2's existing `Auto ping pillars`
setting on the reviewed Risk of Rain 2 Steam build 25921972. It does not require a
client mod. The official PillarRevive DLL is retained without modification.

The original `PlayerRevive.PingPillar()` calls
`LocalUserManager.GetFirstLocalUser().cachedMasterObject`. A dedicated server has
no local player. This plugin replaces only that method's headless execution with
an update to the dead player's existing `CharacterMaster`'s
`PingerController.NetworkcurrentPing` property. PillarRevive's original three
second `Invoke` scheduling and `autoPing` configuration check are unchanged.

The reviewed game's generated setter marks original SyncVar bit 1 dirty;
`PingerController.OnSerialize` sends the original `PingInfo` including the pillar's
existing network identity. A vanilla observer's `OnDeserialize` calls
`OnSyncCurrentPing`, then `SetCurrentPing` and `RebuildPing`. No custom RPC,
message, network prefab, client-side code, or server-side ping UI is created.
If the converted server has a local network client but no local player, the
reviewed original per-pinger `syncVarHookGuard` bool suppresses only the local
UI branch while the setter runs. Its prior value is restored in `finally`.
The original `SetSyncVar`/dirty-bit path is independent of this guard and still
runs; remote clients execute their normal display hook.
The original authority owner's client ignores this SyncVar hook. Consequently
the victim does not see their own automatic marker; other teammates are its
intended recipients. Manual pings retain normal control and can replace it.

Only an active headless server in batch mode with `RAINS_SERVER_TOOLS=1` uses the
replacement. A real complete local user/master/pinger retains upstream behavior;
`NetworkClient.active` alone never permits the known null dereference. A pending
ping during server shutdown is skipped. Missing or unspawned pillar or
owner pingers produce a bounded warning and do not fall back to the null-local-user
path. A ping queue log proves only that the server assigned its original SyncVar,
not that clients received or displayed the marker. There is no polling or forced
refresh. This plugin does not change resurrection, charge conditions, pillar
lifetimes, teleporter interaction locks, curses, or monster generation.

The plugin has a soft BepInEx dependency on `dolso.pillarrevive` for load ordering,
a hard dependency on the already installed `com.bepis.r2api`, and the original
`NoNeedForSync` / `DifferentModVersionsAreOk` compatibility declaration. If
PillarRevive is absent it remains inactive. It checks both exact DLL digests and
the private method/field signatures before installing a Harmony prefix:

| File | SHA-256 |
| --- | --- |
| Official PillarRevive 1.1.2 DLL | `801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051` |
| Original RoR2 build 25921972 DLL | `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c` |
| Reviewed server-patched RoR2 DLL | `73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07` |
| Original multiplayer HLAPI runtime | `76d55b3e90e5fe6c0f8738302b01d54141e5a07931fa4cfa370f6a20832d37cf` |

Unknown digests or signatures refuse the hook and log an error. Keep upstream
`Auto ping pillars = false` on unsupported versions until reviewed; the official
headless bug remains when this compatibility hook cannot install. Deployment
must verify the successful hook installation log before accepting the setting.

Build without changing existing ServerTools or any deployed staging directory:

```powershell
python Compatibility/PillarReviveHeadless/build.py --dotnet dotnet --output output/pillar-safe-ping-build
```

`--dotnet` accepts an absolute SDK executable path. The script builds Release,
executes the audit, and writes the DLL, `audit.json` and `build.json` containing
the assembly/source digests consumed by `tools/pillar_headless_overlay.py`.
Both metadata reports explicitly retain `runtimeVerified = false`.

The Cecil audit validates the actual original game's SyncVar and client display
chain, hook-guard semantics, upstream private signatures, the compiled hook's
absence of UI/command calls, `finally` restoration, exact allowlisted files and
all referenced game/Unity/BepInEx/R2API/Harmony API members. This is static
compatibility verification, not gameplay validation.

Install only `Rains.PillarReviveHeadless.dll` in a new server-side BepInEx plugin
directory, add its hash to the release inventory, and restart an empty server.
Retain existing ServerTools, official mods and game binaries. Check the successful
hook installation message. Actual automatic marker display still needs a death
with another vanilla player present; clean build/API/serialization checks alone
do not certify this gameplay behavior.
