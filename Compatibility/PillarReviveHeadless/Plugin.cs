using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using BepInEx;
using BepInEx.Bootstrap;
using HarmonyLib;
using R2API.Utils;
using RoR2;
using UnityEngine;
using UnityEngine.Networking;
using Path = System.IO.Path;

namespace Rains.PillarReviveHeadless
{
    [BepInPlugin("local.rains.pillarreviveheadless", "Rains PillarRevive Headless", "0.1.0")]
    [BepInDependency("dolso.pillarrevive", BepInDependency.DependencyFlags.SoftDependency)]
    [BepInDependency("com.bepis.r2api", BepInDependency.DependencyFlags.HardDependency)]
    [NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)]
    public sealed class Plugin : BaseUnityPlugin
    {
        private const string PillarDigest = "801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051";
        private static Plugin instance;
        private FieldInfo pillarOwner;
        private PropertyInfo syncVarHookGuard;
        private Harmony harmony;
        private long failedPings;

        private void Awake()
        {
            if (!Application.isBatchMode || Environment.GetEnvironmentVariable("RAINS_SERVER_TOOLS") != "1") return;
            try
            {
                if (!Chainloader.PluginInfos.TryGetValue("dolso.pillarrevive", out var pillar))
                {
                    Logger.LogInfo("PillarRevive absent; headless ping compatibility inactive.");
                    return;
                }
                var assembly = pillar.Instance.GetType().Assembly;
                // A new game or mod must be reviewed before patching private code.
                if (Digest(pillar.Location) != PillarDigest) throw new InvalidOperationException("mod-digest");
                // Preloader Assembly.Load(byte[]) can leave Assembly.Location empty.
                var gameDigest = Digest(Path.Combine(Application.dataPath, "Managed", "RoR2.dll"));
                if (gameDigest != "73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07" &&
                    gameDigest != "48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c")
                    throw new InvalidOperationException("game-digest");
                if (Digest(Path.Combine(Application.dataPath, "Managed", "com.unity.multiplayer-hlapi.Runtime.dll")) !=
                    "76d55b3e90e5fe6c0f8738302b01d54141e5a07931fa4cfa370f6a20832d37cf")
                    throw new InvalidOperationException("network-runtime-digest");
                const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                var type = assembly.GetType("PillarRevive.PlayerRevive", true);
                var ping = type.GetMethod("PingPillar", flags, null, Type.EmptyTypes, null);
                pillarOwner = type.GetField("networkUser", flags);
                if (!typeof(Component).IsAssignableFrom(type) || ping == null || ping.IsStatic ||
                    ping.ReturnType != typeof(void) || pillarOwner == null || pillarOwner.FieldType != typeof(NetworkUser))
                    throw new MissingMemberException();
                syncVarHookGuard = typeof(NetworkBehaviour).GetProperty("syncVarHookGuard", flags);
                var networkPing = typeof(PingerController).GetProperty("NetworkcurrentPing", flags);
                if (syncVarHookGuard == null || syncVarHookGuard.PropertyType != typeof(bool) ||
                    syncVarHookGuard.GetGetMethod(true) == null || syncVarHookGuard.GetSetMethod(true) == null ||
                    networkPing == null || networkPing.PropertyType != typeof(PingerController.PingInfo) ||
                    networkPing.GetSetMethod() == null)
                    throw new MissingMemberException();
                instance = this;
                harmony = new Harmony("local.rains.pillarreviveheadless");
                harmony.Patch(ping, prefix: new HarmonyMethod(typeof(Plugin).GetMethod(nameof(BeforePingPillar), BindingFlags.Static | BindingFlags.NonPublic)));
                Logger.LogInfo("Reviewed PillarRevive 1.1.2 headless ping hook installed; uses original player-master ping SyncVar.");
            }
            catch (Exception exception)
            {
                if (harmony != null) harmony.UnpatchSelf();
                harmony = null;
                instance = null;
                Logger.LogError("Headless pillar ping compatibility refused or failed: " + exception.GetType().Name + ". Keep Auto ping pillars disabled until repaired.");
            }
        }

        private static bool BeforePingPillar(Component __instance)
        {
            var plugin = instance;
            if (plugin == null) return true;
            // A local network client does not imply a LocalUser on the converted
            // dedicated binary. Only an actual complete local pinger can safely
            // retain upstream's listen-host behavior.
            var localUser = LocalUserManager.GetFirstLocalUser();
            if (localUser != null && localUser.cachedMasterObject &&
                localUser.cachedMasterObject.GetComponent<PingerController>()) return true;
            // A pending Invoke can outlive a shutdown; do not run the known-null
            // headless LocalUser path while the original server is stopping.
            if (!NetworkServer.active) return false;
            try
            {
                // The victim's CharacterMaster survives body death: upstream's
                // OnCharged uses the same networkUser.master to respawn the body.
                var owner = plugin.pillarOwner.GetValue(__instance) as NetworkUser;
                var master = owner ? owner.master : null;
                var pinger = master ? master.GetComponent<PingerController>() : null;
                var target = __instance ? __instance.GetComponent<NetworkIdentity>() : null;
                if (!pinger || !pinger.isServer || pinger.netId == NetworkInstanceId.Invalid ||
                    !target || target.netId == NetworkInstanceId.Invalid)
                {
                    plugin.RecordFailure("missing-spawned-pillar-or-owner-pinger");
                    return false;
                }
                // NetworkcurrentPing's generated setter marks SyncVar dirty bit 1.
                // Its original serializer sends PingInfo and target netId to the
                // master's observers. Vanilla clients rebuild the original ping;
                // no custom message, prefab, client plugin or server UI is used.
                // The authority owner ignores server ping changes by stock design;
                // all other teammates can see this victim-owned automatic marker.
                var pingInfo = new PingerController.PingInfo
                {
                    active = true,
                    origin = __instance.transform.position,
                    normal = Vector3.zero,
                    targetNetworkIdentity = target
                };
                if (NetworkServer.localClientActive)
                {
                    // A converted binary can have a local network client without
                    // a LocalUser. Suppress only the generated host-side UI hook,
                    // preserving SetSyncVar, dirty bits and remote serialization.
                    // This reviewed per-component bool is restored in finally;
                    // no global network state or client authority is changed.
                    bool previous = (bool)plugin.syncVarHookGuard.GetValue(pinger, null);
                    plugin.syncVarHookGuard.SetValue(pinger, true, null);
                    try { pinger.NetworkcurrentPing = pingInfo; }
                    finally { plugin.syncVarHookGuard.SetValue(pinger, previous, null); }
                }
                else pinger.NetworkcurrentPing = pingInfo;
                plugin.Logger.LogInfo("Pillar auto ping queued through original player-master SyncVar; client display not certified by this log.");
            }
            catch (Exception exception)
            {
                plugin.RecordFailure(exception.GetType().Name);
            }
            // Never fall back to the known-null LocalUser dereference on headless.
            return false;
        }

        private void RecordFailure(string reason)
        {
            failedPings++;
            if (failedPings <= 3 || failedPings % 60 == 0)
                Logger.LogWarning("Pillar auto ping was not sent: " + reason + " (count=" + failedPings + ").");
        }

        private void OnDestroy()
        {
            if (ReferenceEquals(instance, this)) instance = null;
            if (harmony != null) harmony.UnpatchSelf();
        }

        private static string Digest(string path)
        {
            using (var file = File.OpenRead(path))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
        }
    }
}
