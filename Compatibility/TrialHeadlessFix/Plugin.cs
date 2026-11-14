using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using System.Security.Cryptography;
using BepInEx;
using HarmonyLib;
using R2API.Utils;
using RoR2;
using RoR2.Items;
using RoR2.Quests;
using RoR2.Quests.TrialQuests;
using UnityEngine;
using UnityEngine.Networking;
using Path = System.IO.Path;

namespace Rains.TrialHeadlessFix
{
    // Server-only compatibility fix for DLC4 "Trials of N'kuhana" on a dedicated server
    // (NetworkServer.active && !NetworkServer.localClientActive).
    //
    // Root cause: UNet-weaver generated SyncVar setters on RoR2.TrialController only run
    // the SyncVar hook on the server when NetworkServer.localClientActive (listen host).
    // TrialController relies on those hooks for server-side logic:
    //   NetworkvariantIndex        -> OnSyncVariantIndex        -> TrialVariantEventRelay.OnVariantChosen (prepareSceneForVariant)
    //   NetworkhasTrialStarted     -> OnHasTrialStartedSet      -> onTrialStartedGlobal + OnVariantBegin (QuestStarter.BeginQuestServer)
    //   Network_trialControllerState -> OnTrialControllerStateSet -> restore inventories / success / failure events
    // On a dedicated server none of these run, so the trial never starts.
    // Fix: in exactly these three setters, use NetworkServer.active instead of
    // NetworkServer.localClientActive, i.e. run the hook on the authoritative server exactly
    // like a listen host does. Clients are untouched (this plugin is server-only).
    [BepInPlugin(Id, "Rains Trial Headless Fix", "0.1.0")]
    [BepInDependency("com.bepis.r2api", BepInDependency.DependencyFlags.HardDependency)]
    [NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)]
    public sealed class Plugin : BaseUnityPlugin
    {
        public const string Id = "local.rains.trialheadlessfix";
        private const string ReviewedGameDigest = "73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07";
        private const string ReviewedNetworkDigest = "76d55b3e90e5fe6c0f8738302b01d54141e5a07931fa4cfa370f6a20832d37cf";

        private static Plugin instance;
        private Harmony harmony;
        private Harmony diagnostics;
        private static int replacedInCurrentSetter;
        private static FieldInfo pendingChangesField;
        private static FieldInfo candidateInventoryField;
        private static FieldInfo relayChosenField;
        private static long prunedContagionEntries;

        private static readonly string[] HookedSetters =
        {
            "set_NetworkvariantIndex",
            "set_NetworkhasTrialStarted",
            "set_Network_trialControllerState",
        };

        private void Awake()
        {
            if (!Application.isBatchMode)
            {
                Logger.LogInfo("Not a headless server; inactive.");
                return;
            }
            instance = this;
            try
            {
                var gameDigest = Digest(Path.Combine(Application.dataPath, "Managed", "RoR2.dll"));
                if (gameDigest != ReviewedGameDigest) throw new InvalidOperationException("game-digest " + gameDigest);
                var netDigest = Digest(Path.Combine(Application.dataPath, "Managed", "com.unity.multiplayer-hlapi.Runtime.dll"));
                if (netDigest != ReviewedNetworkDigest) throw new InvalidOperationException("network-runtime-digest " + netDigest);

                harmony = new Harmony(Id);
                var transpiler = new HarmonyMethod(typeof(Plugin).GetMethod(nameof(UseServerActiveForHook), BindingFlags.Static | BindingFlags.NonPublic));
                foreach (var name in HookedSetters)
                {
                    var setter = AccessTools.DeclaredMethod(typeof(TrialController), name);
                    if (setter == null) throw new MissingMethodException("TrialController", name);
                    replacedInCurrentSetter = 0;
                    harmony.Patch(setter, transpiler: transpiler);
                    if (replacedInCurrentSetter != 1)
                        throw new InvalidOperationException(name + " localClientActive sites=" + replacedInCurrentSetter);
                }
                Logger.LogInfo("TrialController SyncVar hooks now run on the dedicated server (3 setters patched).");
            }
            catch (Exception e)
            {
                harmony?.UnpatchSelf();
                harmony = null;
                Logger.LogError("Trial headless fix refused/failed, nothing patched: " + e);
                return;
            }

            // Independent defensive fix: ContagiousItemManager keeps destroyed inventories in its static
            // pendingChanges list; StepInventoryInfection then throws NullReferenceException every
            // FixedUpdate, which aborts the rest of RoR2Application.onFixedUpdate and fixedTimeTimers.
            try
            {
                pendingChangesField = AccessTools.DeclaredField(typeof(ContagiousItemManager), "pendingChanges");
                var candidateType = AccessTools.Inner(typeof(ContagiousItemManager), "InventoryReplacementCandidate");
                candidateInventoryField = candidateType == null ? null : AccessTools.DeclaredField(candidateType, "inventory");
                var process = AccessTools.DeclaredMethod(typeof(ContagiousItemManager), "ProcessPendingChanges");
                if (pendingChangesField == null || candidateInventoryField == null || process == null ||
                    candidateInventoryField.FieldType != typeof(Inventory) || !typeof(IList).IsAssignableFrom(pendingChangesField.FieldType))
                    throw new MissingMemberException("ContagiousItemManager layout");
                harmony.Patch(process, prefix: new HarmonyMethod(typeof(Plugin).GetMethod(nameof(PruneDestroyedInventories), BindingFlags.Static | BindingFlags.NonPublic)));
                Logger.LogInfo("ContagiousItemManager destroyed-inventory guard installed.");
            }
            catch (Exception e)
            {
                Logger.LogWarning("Contagion guard not installed (trial fix still active): " + e.Message);
            }

            InstallDiagnostics();
        }

        private static IEnumerable<CodeInstruction> UseServerActiveForHook(IEnumerable<CodeInstruction> instructions)
        {
            var localClientActive = AccessTools.PropertyGetter(typeof(NetworkServer), nameof(NetworkServer.localClientActive));
            var replacement = AccessTools.Method(typeof(Plugin), nameof(ServerRunsSyncVarHooks));
            foreach (var ins in instructions)
            {
                if (ins.Calls(localClientActive))
                {
                    replacedInCurrentSetter++;
                    yield return new CodeInstruction(OpCodes.Call, replacement).MoveLabelsFrom(ins);
                }
                else yield return ins;
            }
        }

        // Listen host: true (unchanged). Dedicated server: true (the fix). Pure client: false (unchanged).
        public static bool ServerRunsSyncVarHooks() => NetworkServer.active;

        private static void PruneDestroyedInventories()
        {
            if (pendingChangesField.GetValue(null) is not IList list || list.Count == 0) return;
            int pruned = 0;
            for (int i = list.Count - 1; i >= 0; i--)
            {
                var inv = candidateInventoryField.GetValue(list[i]) as Inventory;
                if (!inv) { list.RemoveAt(i); pruned++; }
            }
            if (pruned > 0)
            {
                prunedContagionEntries += pruned;
                instance?.Logger.LogWarning($"[contagion] removed {pruned} pending transformation(s) for destroyed inventories (total={prunedContagionEntries}).");
            }
        }

        // ---------- diagnostics (log only, no behavior change) ----------
        private void InstallDiagnostics()
        {
            try
            {
                diagnostics = new Harmony(Id + ".diag");
                relayChosenField = AccessTools.DeclaredField(typeof(TrialVariantEventRelay), "chosen");
                Post(AccessTools.DeclaredMethod(typeof(TrialController), "OnStartServer"), nameof(DiagStartServer));
                Post(AccessTools.DeclaredMethod(typeof(TrialController), "OnHasTrialStartedSet"), nameof(DiagTrialStarted));
                Post(AccessTools.DeclaredMethod(typeof(TrialController), "OnTrialControllerStateSet"), nameof(DiagState));
                Post(AccessTools.DeclaredMethod(typeof(QuestRunner), "SetNewQuest"), nameof(DiagQuest));
                Post(AccessTools.DeclaredMethod(typeof(BaseTrialQuest), "SpawnTrialTimersOnPlayersServer"), nameof(DiagTimer));
                Post(AccessTools.DeclaredMethod(typeof(CreateItemPotentialFromInventory), "SpawnPotentialFromInventory"), nameof(DiagPotential));
                Logger.LogInfo("Trial diagnostics installed (log only).");
            }
            catch (Exception e)
            {
                Logger.LogWarning("Trial diagnostics partially unavailable: " + e.Message);
            }
        }

        private void Post(MethodInfo m, string name)
        {
            if (m == null) { Logger.LogWarning("diag target missing for " + name); return; }
            diagnostics.Patch(m, postfix: new HarmonyMethod(typeof(Plugin).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)));
        }

        private static void Log(string s) => instance?.Logger.LogInfo("[trial] " + s);

        private static void DiagStartServer(TrialController __instance)
        {
            try
            {
                int idx = __instance.NetworkvariantIndex;
                var variants = __instance.trialVariants;
                var relay = variants != null && idx >= 0 && idx < variants.Length ? variants[idx] : null;
                bool chosen = relay && relayChosenField != null && (bool)relayChosenField.GetValue(relay);
                Log($"OnStartServer scene={SceneCatalog.mostRecentSceneDef?.cachedName} variants={variants?.Length} index={idx} " +
                    $"variant={(relay ? relay.customName : "none")} preparedOnServer={chosen} safekept={(__instance.inventorySafekeepController ? __instance.inventorySafekeepController.hasSafekeptInventories : false)} " +
                    $"localClientActive={NetworkServer.localClientActive} clientActive={NetworkClient.active} " +
                    $"timerLeft={(DLC4ProgressionController.instance && DLC4ProgressionController.instance.trialSelector ? DLC4ProgressionController.instance.trialSelector.GetRemainingTrialTimeServer() : -1f)}");
            }
            catch (Exception e) { Log("OnStartServer diag error " + e.GetType().Name); }
        }

        private static void DiagTrialStarted(TrialController __instance, bool hasTrialStarted)
        {
            if (NetworkServer.active) Log($"OnHasTrialStartedSet({hasTrialStarted}) ran on server; onTrialStartedGlobal/OnVariantBegin invoked");
        }

        private static void DiagState(TrialController __instance, TrialController.TrialControllerState newState)
        {
            if (NetworkServer.active) Log($"trial state -> {newState} (server hook ran)");
        }

        private static void DiagQuest(QuestRunner __instance, BaseQuest newQuest)
        {
            if (NetworkServer.active && newQuest != null) Log($"QuestRunner.SetNewQuest {newQuest.GetType().FullName} on {__instance.name}");
        }

        private static void DiagTimer(BaseTrialQuest __instance)
        {
            if (NetworkServer.active && DLC4ProgressionController.instance && DLC4ProgressionController.instance.trialSelector)
                Log($"trial countdown started remaining={DLC4ProgressionController.instance.trialSelector.GetRemainingTrialTimeServer():0.0}s quest={__instance.GetType().Name}");
        }

        private static void DiagPotential(CreateItemPotentialFromInventory __instance, Inventory inventory)
        {
            if (!NetworkServer.active) return;
            var master = inventory ? inventory.GetComponent<CharacterMaster>() : null;
            Log($"SpawnPotentialFromInventory on {__instance.name} master={(master ? master.name : "none")} acquiredItems={(inventory ? inventory.itemAcquisitionOrder.Count : -1)}");
        }

        private void OnDestroy()
        {
            diagnostics?.UnpatchSelf();
            harmony?.UnpatchSelf();
            if (ReferenceEquals(instance, this)) instance = null;
        }

        private static string Digest(string path)
        {
            using var file = File.OpenRead(path);
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
        }
    }
}
