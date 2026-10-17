# Exact upstream FPTS compatibility candidate

This directory vendors the unmodified upstream source of FixPluginTypesSerialization at commit `7b7b2a596c18f1f9bb4ae9ddedfe1eea18cecb7c` from https://github.com/xiaoxiao921/FixPluginTypesSerialization . `upstream-provenance.json` records every git blob SHA256. Preserve `upstream/LICENSE` (LGPL-3.0) and the full source when distributing this local build. This is a local candidate built from that source, not the Thunderstore 1.0.4 binary.

The official Thunderstore 1.0.4 DLL failed during the real router test after accepting the exact PDB offsets: `IsFileCreated.OnIsFileCreated -> v2021.v1.AbsolutePathString.ToStringAnsi` raised `Illegal byte sequence` and the container exited. Its old IsFileCreated parameter handler treats the argument as a whole Unity string object. This revision adds `v2021.v2.IsFileCreatedParam`, applicable since Unity 2021.2, which reads a StringView with a pointer at offset 0 and a length at offset 8. The 2023 StringStorageDefaultV3 layout must not be forced onto this Unity 2021 build.

The complete, GUID-matched PDB independently identifies IsFileCreated at RVA 0x554320. That function's first native instructions read `[rcx+8]` as the length, consistent with the added StringView handler. Its 2021.3.45f2 offset table agrees with all eight exact-PDB values; the missing/inlined IsAssemblyCreated function uses the upstream safe-zero/IsFileCreated fallback. These facts establish a plausible ABI correction, not successful gameplay.

Build with Python and .NET SDK 8.0.426 (the validated compiler):

```powershell
python Compatibility/FixPluginTypesSerialization/build.py --dotnet dotnet --output output/fpts-master-candidate-new
```

The output must be a new directory. The script checks vendored source hashes, runs only the netstandard2.1 target, uses NuGet locked mode, sets a stable source path map, and emits the candidate DLL, upstream license, provenance, dependency-lock hash, DLL hash, compiler version, command and full build log. It never changes a profile, game, router or container. `upstream/src/FixPluginTypesSerialization/packages.lock.json` pins the resolved transitive dependencies as well as upstream BepInEx.Core 5.4.21, Costura.Fody 5.4.0 and MSFTCompressionCab 1.0.0. Costura embeds the CAB helper; do not copy other BepInEx/MonoMod core files from build dependencies into the game.

The build produces warnings for upstream native-layout fields and NU1701 because the upstream CAB package targets .NET Framework; that optional download path is not exercised by the offline cache tests. Keep these limitations visible. No TLS verification is disabled.

For a runtime candidate, copy the DLL and exact-PDB config as a single local overlay with a new recorded DLL hash, source commit, config hash and runtime inventory. Preserve the original Thunderstore archive/lock; clearly record the local replacement rather than claiming the archive contains the fork DLL. Do not pass the local build to `tools/unity_symbols.py` under an official SHA allowlist: the tool correctly refuses unreviewed DLLs. The earlier official 1.0.4 cache contains the same source-compatible keys and exact function offsets, but local-build provenance must be separately recorded.

On any UnityPlayer or FPTS source update, regenerate offsets for that exact PE/PDB, re-audit parameter layouts and handler selection, rebuild from a newly explicit pin, then test the native callbacks, lobby, client authentication, run start, stage changes, restart and soak. Retain prior artifacts for rollback. Synthetic native StringView tests (zero/19/59 byte non-NUL buffers) passed against the actual candidate DLL; Wine/Unity native hooks and multiplayer remain unverified until router evidence is collected.
## Local audited maintenance overlay

Runtime checkpoint (2026-10-18): this maintained native DLL (`1d0ac76e...`) completed the V6 Wine lobby and a real Steam client's first-stage load. The isolated client observed a player-controlled body and replicated monster-team bodies. Controlled Docker stop returned zero, but the supervisor uses `wineserver -k`; this is not proof that Unity's native destruction callback completed. Two-player gameplay, repeated stage transitions, normal Unity shutdown and occupied-session soak remain unverified.

`local-patches.json` applies six files to a separate build-source copy after all original upstream blobs and the dependency lock have passed hash checks. Each patch has exact old/new text and before/after SHA256. The original vendored files remain byte-for-byte unchanged. The build report includes patched inputs, overlay hash and new DLL hash. No native hook is disabled by this overlay.

Five reverse-P/Invoke hook delegates now have static readonly managed roots. The Unity2021 MonoManager now saves the original native scripting-assembly state before replacing names, restores only the original names vector (pointer, label, size and capacity), and preserves the types vector that Unity may legitimately update during AwakeFromLoad. Restore is idempotent; a second injection before restoration is rejected explicitly rather than stacking another untracked native vector. This is a new fail-closed lifecycle constraint; repeated AwakeFromLoad behavior still needs a real Unity test.

The names array is a shallow copy: original Unity-owned string payloads remain shared between the old and injected records. The local fix does not free all copied records, which could double-free shared payloads; it also does not guess ownership of the injected vector or strings after native initialization. Those allocations remain process-lifetime allocations pending actual pointer-ownership evidence. The potential Marshal-HGlobal/Unity allocator mismatch is still an open hypothesis because the Convert callback may receive a native-owned copy of the injected string. No allocator change was made without that evidence.

Run the controlled native-memory test against the actual built DLL:

```powershell
dotnet run --project Compatibility/FixPluginTypesSerialization/tests/FptsMaintenanceTests.csproj -- output/fpts-maintained-candidate/FixPluginTypesSerialization.dll output/mods-candidate/BepInEx/core
```

It verifies exact names-vector restoration, byte-for-byte preservation of changed types, repeated-injection rejection and restore idempotence using only memory owned by the test process. It also inspects callback root fields. It does not invoke native detours or Unity allocators. The maintained candidate passed these checks; this does not prove a fix for the observed high-CPU startup or long-session/shutdown behavior under Wine. Actual runtime remains unverified until separate router evidence.
