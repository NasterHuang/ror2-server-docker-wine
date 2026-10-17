# RoR2Patcher: explicit experimental assembly transforms

This is an offline experimental patcher, **not a complete dedicated-server conversion**. It does not establish that current Steam clients can join. It never rewrites build IDs, disables version checks, changes authentication, or converts Steam initialization failures into success.

## Build and tests

Requires .NET 8 SDK. Runtime output requires the .NET 8 runtime; the game itself uses Unity's runtime independently.

```sh
dotnet build RoR2Patcher/RoR2Patcher.csproj -c Release
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
dotnet publish RoR2Patcher/RoR2Patcher.csproj -c Release --no-self-contained -o output/patcher
```

The console test runner constructs synthetic assemblies and verifies 32 checks including all optional transforms, preservation of the build assignment, idempotent output, source drift, missing optional targets, CLI/source-path protection, actual server-loader call/validity/shutdown instructions, reuse of the built-in dummy user manager, server networking references and deferred initialization. The deferred regression checks require the skipped client block to contain only NOPs and modified branch offsets to use long encodings. These are structural tests, not Unity execution or multiplayer tests.

## CLI

```sh
# Read only. JSON includes source SHA256, module identity, relevant IL, and client API dependencies.
dotnet output/patcher/RoR2Patcher.dll --inspect --input /game/Risk\ of\ Rain\ 2_Data/Managed/RoR2.dll --report output/audit.json

# A separate staging output, never the original game file.
dotnet output/patcher/RoR2Patcher.dll --input /game/Risk\ of\ Rain\ 2_Data/Managed/RoR2.dll --output output/RoR2.dll --manifest RoR2Patcher/manifests/steam-build-25921972.experimental.json --report output/result.json
```

Exit 0 means inspection or an exact structural patch succeeded. Exit 1 means failure; stderr contains a JSON error. Successful reports go to `--report`, or stdout when omitted. `gameRuntimeVerified` is always `false`. Do not use a patch report as a readiness check.

Apply requires a manifest. The tool checks the full original DLL SHA256, exact method/reference signatures and instruction offsets. It preflights the complete transform group before writing. Existing outputs are replaced atomically only after successful serialization and readback. Repeating against the same **original** DLL yields identical output and `status: unchanged`; feeding a patched DLL back as input is refused by SHA256. Do not chain patched inputs or trust a `.bak` as evidence of an original build. Strong-named inputs are rejected. This tool does not make external files or dependent assemblies compatible.

## Manifest

`manifests/steam-build-25921972.experimental.json` is based on offline inspection of a user-supplied Steam installation, manifest build 25921972, SHA256 `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`. Its three transforms were applied to a separate output copy and read back successfully. A subsequent baseline Wine/router startup reached Unity catalog/audio loading but logged `SteamAPI_Init returned false` and exposed no working A2S query endpoint. **This baseline is not a usable dedicated server.** A different game binary is deliberately refused, even when its displayed version is the same.

The manifest supports:

* `patches`: exactly one `SteamworksServerManager` instance setter preceded by `ldc.i4.0`, changed in place to `ldc.i4.1`. The setter must be exactly a reviewed instance `void set_DedicatedServer(bool)`.
* Optional `startup`: exact `Console.RunConfigsAfterLoad` call window for `SubmitCmd(null, "exec autoexec", false)`, followed by an inserted `CollectHandlers()` and `SubmitCmd(null, "exec server_startup", false)`. Supports `this` or an explicitly named static `Console.get_instance()`. Rejects branch targets, methods with exception handlers, and preexisting startup injection. No arbitrary startup string is accepted.
* Optional `lobby`: exact `stloc.0; ldarg.0; ldloc.0; newobj LobbyData(LobbyDataSetupState)` window converted to `pop; ldarg.0; nop; newobj LobbyData()`. Keeping instruction objects preserves instruction references. Rejects branch targets, exception handlers and any other use of local zero. This changes initial lobby data only; it does not remove the Steam client dependency of `SteamworksLobbyManager.Init()`.
* Optional `appIds`: explicit method and offset pairs for `632360` to `1180760` in `SteamworksServerManager` or `RoR2Application`. There is no global literal replacement. The supplied current-build manifest leaves this empty because the Steam server SDK normally advertises the game AppID; selecting the SteamCMD dedicated-tool ID is a separate behavior change that has not been justified for this build.
* Optional `serverBootstrap`: exact current-build client-loader/unloader delegate methods replaced with actual Steam game-server initialization and shutdown. It configures Facepunch using `UnityEngine.Application.platform`, creates initial lobby data without invoking client-lobby APIs, calls `ServerManagerBase<SteamworksServerManager>.StartServer()`, and returns `Server.Instance.IsValid` (or `false` if no instance exists). The existing `steamworksFailed` handling consumes that real result. It does not return constant success, rewrite authentication or change version checks. The unloader calls the actual `StopServer()`. With `useDummyUserManager: true`, it replaces the one Steam user-manager construction with the existing game `UserManagerDummy`, preserving the guarded Steam-specific setup. Use the separate `steam-build-25921972.server-bootstrap.experimental.json` profile only for runtime diagnostics. Early initialization ordering, later server recreation, platform service dependencies and multiplayer behavior remain unverified.
* `serverBootstrap.useServerNetworking`: switches four reviewed server methods (`UpdateServer`, `ForceCloseAllConnections`, `CheckSteamworks`, `GetClient`) from the client singleton to the actual server singleton. `GetClient` also switches its paired SteamId getter so the receiver type stays valid. Exact source method/offset/call signatures must match. The server-only profile requires `steam_p2p_use_steam_server 1` before `host`; the current game's default is zero and selects the client receive interface.
* `serverBootstrap.deferUntilHost`: the current diagnostic profile after real early-bootstrap failure. It skips the complete client-only initialization block in `InitializeGameRoutine.MoveNext` with an explicit branch; no client loader is called and no initialization result or failure field is forged. Before this branch, it preserves `Config.ForUnity(Application.platform.ToString())` and initial lobby data. The real `SteamworksServerManager` is created only by the ordinary post-catalog `InitPlatformServer` host path; a missing instance or false `IsValid` throws an explicit exception before `InitP2P`. It checks that no external branch enters the skipped window and that the new branch stays within the same exception-handler region. Unload calls the real server shutdown. Use `steam-build-25921972.deferred-server.experimental.json` for this complete experimental selection.

Known failed profiles are retained as reproducible evidence, not deployment recommendations. The early `server-bootstrap`/`server-networking` profiles were tested on the router and failed with `ArgumentNullException: sourceArray` in `RuleBook.SetToDefaults -> ServerManagerBase<T> -> SteamworksServerManager`: game catalogs were not ready when the client-loader delegate ran. The deferred profile exists specifically to fix that ordering; its structural tests pass, but successful runtime startup and multiplayer still need verification. The baseline profile failed real Steam client initialization. None is advertised as stable.

The corrected deferred candidate `73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07` subsequently reached a real router lobby and `steamworksServer.IsValid=True`; the original orphaned `dup` failure no longer occurred. This establishes startup progress only. The constructor logs `LoggedOn=False` immediately after `LogOnAnonymous()` (original IL offsets `0x018b` and `0x01a3`), before asynchronous login callbacks can complete. Its ordinary `onUpdate` subscription invokes `SteamworksServerManager.Update`, which calls `BaseSteamworks.Update`; obtain a later `steam_server_print_info` result before judging login. A2S alone is insufficient evidence of authentication or client compatibility.

The current binary also logs `Network message MsgType.Highest + 22 is unregistered` during ordinary `CollectHandlers()`. This is message ID 69, the `UmsgType.SetJetpackJumpState` constant. Offline inspection found no handler attribute for ID 69 and no network sender using its inlined value in the original assembly. The collector scans the whole numeric range 48 through 87 and warns about this hole. The actual server authentication handler, `ServerAuthManager.HandleSetClientAuth`, uses ID 74 with `server=True`. Do not suppress the warning or invent an authentication handler to conceal it; real connection testing must still verify that authentication is registered and runs.

The manifest is an explicit review artifact, not a signature or a security boundary against a malicious operator. Do not generate one automatically from every changed DLL. Review new builds, update synthetic coverage if instruction patterns change, and repeat actual game tests.

## Current Steam build: independent startup remains incomplete

Offline IL evidence from the current supplied binary:

1. `RoR2Application.AssignBuildId()` reads `UnityEngine.Application.version`. `ServerAuthManager.HandleSetClientAuth` calls the real `GetBuildId()` at IL offset 278. Both remain unchanged.
2. `PlatformSystems.Init()` registers `SteamworksClientManager.Init()` at offset 27. It constructs the Steam lobby/user/save/achievement/entitlement platform services. The client manager's constructor creates a real `Facepunch.Steamworks.Client(632360)`, checks `IsValid`, `RestartIfNecessary`, API DLL validity and subscription. Bypassing those checks is not an independent server implementation.
3. `InitializeGameRoutine.MoveNext()` calls the registered `loadSteamworksClient` delegate at offsets 787 onward, setting `steamworksFailed` at 808 after a false result. This real failure result remains intact.
4. `SteamworksLobbyManager.Init()` starts with `Client.get_Instance().Lobby` before reaching the patched lobby-data window at 290. The lobby-data transform cannot substitute a working platform service.
5. `NetworkManagerSystemSteam.InitP2P()` contains a real server SDK path, server callbacks and `cvSteamP2PUseSteamServer` selection. However `UpdateServer()` still uses `Client.get_Instance().Networking` at offset 48 for `SteamNetworkConnection`, and `CheckSteamworks()` accepts only a client singleton. A server endpoint being valid does not resolve these dependencies.
6. `ServerManagerBase<T>.StartServer()` disposes an existing instance, uses `Activator.CreateInstance<T>()`, and clears disposed instances. Calling this early as a fake client loader is unsafe without establishing convar/system-initializer order and handling the later second call during network host creation.

A complete server-only implementation needs a distinct boot path that initializes the actual Steam game-server API, returns its real validity result, uses server-side network/auth interfaces, supplies working platform services without local Steam users, and owns orderly shutdown. Authentication and client entitlement semantics must be preserved. The current assembly contains an existing concrete `UserManagerDummy`, which the optional bootstrap reuses. It contains no equivalent dedicated/null `LobbyManager`, `SaveSystem` or `AchievementSystem`; the existing Steam services remain subject to real runtime validation. Stubbing them all to success would hide broken behavior. This work needs a Unity runtime test loop and at least one real client. The included transforms provide reviewed building blocks and audit evidence; they do not claim that this broader conversion is finished.

Official reference-download evidence: SteamCMD anonymously installed Steamworks SDK Redist app 1007, build 25329704, successfully. The current public app 1180760 metadata reports Windows64 only, build 20243729, depot 1180761 manifest 4364034953916804679 with size/download zero. A Linux install is rejected as `Invalid platform`. No old dedicated game assembly was obtained for comparison; the older server implementation must not be inferred from a successful empty-tool install. Proprietary game/SDK files are kept outside version control and are not distributed by this repository.

## SeekersPatcher dependency compatibility (2026-10-17)

The first real modded startup with the original candidate dependency lock failed in `SeekersPatcher 1.3.7` with `Sequence contains no matching element`. Inspection of that published patcher binary identifies `PatchRoR2` IL `0x03ff`/`0x041e`: it searches `PlayerCharacterMasterController.Fields.First(name == "jumpWasClaimed")`, but the original build 25921972 no longer contains that field. None of the dedicated transforms modifies this type, so changing the dedicated coroutine or suppressing the preloader exception would not repair the cause.

The [official 1.4.4 package](https://thunderstore.io/c/riskofrain2/p/pseudopulse/SeekersPatcher/v/1.4.4/) incorporates the 1.4.2 missing-field fix. Its actual `PatchMissingFields` adds `jumpWasClaimed` explicitly rather than depending on the removed source field. Its published archive SHA256 is `e0f4900fb6bab73aabb2234b6ba5f50b37bb9b790fba9f0e6c5dd525004a1509`. The package also requires its included `SeekersPatcherDLL.dll` runtime plugin; copying only the preloader patcher is incomplete. No upstream repository URL is supplied in its API or package manifest, so the inspection evidence is the published package's actual IL and changelog, not an assumed source repository.

An isolated staging lock `output/candidate-v2.lock.json` (SHA256 `f0e7cdee5812082427daddcc3d9b9f80e778c9e2b926a08bafec1c299de16926`) explicitly selects SeekersPatcher 1.4.4 alongside the previous three roots. `tools/mods.py` generated `output/mods-candidate-v2` without changing the original failed lock or staging directory. This structural diagnosis does not certify the complete modded runtime; repeat real preloader, plugin-chain, client and run tests. In particular, the separate Unity serialization/PDB failure requires its own repair.

## Audit of removed upstream behavior

The original implementation rewrote `AssignBuildId` to a historical hardcoded version and replaced the server auth build comparison with another hardcoded version, permitting a misleading handshake between incompatible game states. It also globally replaced client AppID literals, changed `steamworksFailed = true` to false, assumed the first overload of `SubmitCmd`, and removed IL instruction objects without verifying branch/exception targets. Those behaviors have been removed. Neither version-string rewriting nor a successful UDP query proves content/network compatibility.

## Direct-connect alternative investigated (2026-10-17)

Primary source inspected without copying implementation: [RoR2DirectConnect](https://github.com/Cindy-Master/Risk-of-Rain-2-mods-cindy_master/tree/e14c4a49cbd9f8f85880320c0ff29facbc547c0d/RoR2DirectConnect), repository HEAD `e14c4a49cbd9f8f85880320c0ff29facbc547c0d`, commit date 2026-07-01. `Plugin.cs` reports 2.0.9 while its repository `manifest.json` reports 2.0.0. No LICENSE/COPYING was found in that Git tree; no implementation code has been incorporated here. This does not establish the contents or license of a separate Thunderstore release.

This plugin activates direct networking when a player uses UI or `dc_host`/`dc_connect`; its global direct-connect flag defaults to false. It patches later hosting/P2P/lobby/authentication behavior, but does **not** replace `PlatformSystems.Init`, `loadSteamworksClient`, or early client initialization. It therefore supplies no demonstrated solution for booting a standalone Linux process without a Steam client. Its private UNet mode also skips real server creation/authentication and supplies a dummy ticket; this must not be represented as Steam-authenticated multiplayer. A separate explicitly selected private-server protocol with its own password/access controls could use direct UNet transport, but would still require independent bootstrap implementation and real client tests.
