using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using BepInEx;
using R2API.Utils;
using UnityEngine;

namespace Rains.ServerTools
{
    [BepInPlugin("local.rains.clientwwise", "Rains Client Wwise Compatibility", "0.1.0")]
    [BepInDependency("___riskofthunder.RoR2BepInExPack", BepInDependency.DependencyFlags.HardDependency)]
    [NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)]
    public sealed class ClientWwiseCompatibility : BaseUnityPlugin
    {
        public static string State { get; private set; } = "disabled";

        private void Awake()
        {
            if (Environment.GetEnvironmentVariable("RAINS_RESTORE_CLIENT_WWISE") != "1" || !Application.isBatchMode)
                return;
            try
            {
                // This is a client binary with its real Wwise module, not a stripped
                // Unity server build. Exact reviewed files are mandatory.
                string game = Digest(Path.Combine(Application.dataPath, "Managed", "RoR2.dll"));
                if (game != "73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07" &&
                    game != "48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c")
                    throw new InvalidOperationException();
                if (Digest(Path.Combine(Application.dataPath, "Plugins", "x86_64", "AkSoundEngine.dll")) !=
                    "e734b90f089d499b01cfa926ff855e87b2133d299d5ad18c8d7a6414b16cde47")
                    throw new InvalidOperationException();
                Assembly pack = null;
                foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
                    if (assembly.GetName().Name == "RoR2BepInExPack")
                    {
                        if (pack != null) throw new InvalidOperationException();
                        pack = assembly;
                    }
                if (pack == null || Digest(pack.Location) !=
                    "cf25aafa7fa9b6f872fc393a222858c75a8d631acd51da9928a560e3d0df4cc7")
                    throw new InvalidOperationException();
                var type = pack.GetType("RoR2BepInExPack.ModCompatibility.SaferWWise", true);
                var disable = type.GetMethod("Disable", BindingFlags.Static | BindingFlags.NonPublic);
                if (disable == null || disable.GetParameters().Length != 0) throw new MissingMethodException();
                // Use the upstream's own Undo path for its batch-mode early-failure
                // hooks. Never fake AK_Success, pendingLoads, callbacks or readiness.
                disable.Invoke(null, null);
                State = "original-native-calls-restored";
                Logger.LogInfo("Restored original Wwise calls for reviewed client binary; real audio initialization and bank callbacks are still required.");
            }
            catch (Exception exception)
            {
                State = "restore-failed";
                Logger.LogError("Client Wwise compatibility refused or failed: " + exception.GetType().Name);
            }
        }

        private static string Digest(string path)
        {
            using (var file = File.OpenRead(path))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
        }
    }
}
