using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;

class Program
{
    static readonly List<string> checks = new();
    static void Check(bool value, string label)
    {
        if (!value) throw new InvalidOperationException(label);
        checks.Add(label);
    }
    static bool Calls(MethodDefinition m, string text) => m.HasBody && m.Body.Instructions.Any(i => i.Operand is MethodReference r && r.FullName.Contains(text));
    static string Hash(string file) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();
    static void Main(string[] args)
    {
        string root = Path.GetFullPath(args[0]), built = Path.GetFullPath(args[1]);
        string managed = Path.Combine(root, "output/source-25921972/Risk of Rain 2_Data/Managed");
        string pillarFile = Path.Combine(root, "output/revive-research/pillar/PillarRevive.dll");
        if (!File.Exists(pillarFile)) pillarFile = Directory.GetFiles(Path.Combine(root, "output/revive-research/pillar"), "PillarRevive.dll", SearchOption.AllDirectories).Single();
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(managed);
        resolver.AddSearchDirectory(Path.Combine(root, "output/mods-candidate/BepInEx/core"));
        foreach (string dir in Directory.GetDirectories(Path.Combine(root, "output/mods-candidate/BepInEx/plugins"), "*", SearchOption.AllDirectories)) resolver.AddSearchDirectory(dir);
        using var game = AssemblyDefinition.ReadAssembly(Path.Combine(managed, "RoR2.dll"));
        using var hlapi = AssemblyDefinition.ReadAssembly(Path.Combine(managed, "com.unity.multiplayer-hlapi.Runtime.dll"));
        using var pillar = AssemblyDefinition.ReadAssembly(pillarFile);
        using var compatibility = AssemblyDefinition.ReadAssembly(built, new ReaderParameters { AssemblyResolver = resolver });
        var pinger = game.MainModule.Types.Single(t => t.FullName == "RoR2.PingerController");
        var setter = pinger.Methods.Single(m => m.Name == "set_NetworkcurrentPing");
        Check(setter.IsPublic && setter.Parameters.Count == 1 && setter.Parameters[0].ParameterType.FullName == "RoR2.PingerController/PingInfo", "original PingInfo setter signature");
        Check(Calls(setter, "NetworkBehaviour::SetSyncVar") && setter.Body.Instructions.Any(i => i.OpCode == OpCodes.Ldc_I4 && (int)i.Operand == 1), "original setter marks SyncVar bit 1");
        Check(Calls(pinger.Methods.Single(m => m.Name == "OnSerialize"), "_WritePingInfo_PingerController"), "original server serializes PingInfo");
        Check(Calls(pinger.Methods.Single(m => m.Name == "OnDeserialize"), "PingerController::OnSyncCurrentPing"), "original client deserializes into ping hook");
        var hook = pinger.Methods.Single(m => m.Name == "OnSyncCurrentPing");
        Check(Calls(hook, "get_hasAuthority") && Calls(hook, "PingerController::SetCurrentPing"), "original client owner exemption and display path");
        Check(Calls(pinger.Methods.Single(m => m.Name == "SetCurrentPing"), "PingerController::RebuildPing"), "original client rebuilds vanilla indicator");
        var behaviour = hlapi.MainModule.Types.Single(t => t.FullName == "UnityEngine.Networking.NetworkBehaviour");
        var guard = behaviour.Properties.Single(p => p.Name == "syncVarHookGuard");
        Check(guard.PropertyType.FullName == "System.Boolean" && guard.GetMethod.IsFamily && guard.SetMethod.IsFamily && guard.GetMethod.Parameters.Count == 0 && guard.SetMethod.Parameters.Count == 1, "protected hook guard signature");
        Check(guard.GetMethod.Body.Instructions.Count == 3 && guard.GetMethod.Body.Instructions[1].OpCode == OpCodes.Ldfld && guard.SetMethod.Body.Instructions.Count == 4 && guard.SetMethod.Body.Instructions[2].OpCode == OpCodes.Stfld, "hook guard only accesses per-component bool");
        var syncVar = behaviour.Methods.Single(m => m.Name == "SetSyncVar");
        Check(Calls(syncVar, "NetworkBehaviour::SetDirtyBit") && !Calls(syncVar, "get_syncVarHookGuard"), "hook guard does not suppress dirty serialization");
        var revive = pillar.MainModule.Types.Single(t => t.FullName == "PillarRevive.PlayerRevive");
        var originalPing = revive.Methods.Single(m => m.Name == "PingPillar");
        Check(!originalPing.IsStatic && originalPing.Parameters.Count == 0 && originalPing.ReturnType.FullName == "System.Void" && revive.Fields.Single(f => f.Name == "networkUser").FieldType.FullName == "RoR2.NetworkUser", "official private hook and owner signature");
        Check(Calls(originalPing, "LocalUserManager::GetFirstLocalUser") && Calls(originalPing, "LocalUser::get_cachedMasterObject"), "official headless null-local-user bug remains isolated");
        var plugin = compatibility.MainModule.Types.Single(t => t.FullName == "Rains.PillarReviveHeadless.Plugin");
        var prefix = plugin.Methods.Single(m => m.Name == "BeforePingPillar");
        Check(Calls(prefix, "PingerController::set_NetworkcurrentPing") && !Calls(prefix, "PingerController::SetCurrentPing") && !Calls(prefix, "PingerController::CallCmdPing") && !Calls(prefix, "PingerController::RebuildPing"), "compiled compatibility uses SyncVar without command or UI");
        Check(prefix.Body.ExceptionHandlers.Any(e => e.HandlerType == ExceptionHandlerType.Finally) && Calls(prefix, "PropertyInfo::SetValue"), "compiled guard restoration has finally");
        Check(!compatibility.MainModule.AssemblyReferences.Any(r => r.Name == "PillarRevive"), "no hard DLL dependency on optional PillarRevive");
        var literals = plugin.Methods.Single(m => m.Name == "Awake").Body.Instructions.Where(i => i.OpCode == OpCodes.Ldstr).Select(i => (string)i.Operand).ToArray();
        Check(literals.Contains(Hash(pillarFile)) && literals.Contains(Hash(Path.Combine(managed, "RoR2.dll"))) && literals.Contains(Hash(Path.Combine(managed, "com.unity.multiplayer-hlapi.Runtime.dll"))), "runtime allowlist matches exact reviewed source files");
        int resolved = 0;
        foreach (var member in compatibility.MainModule.GetMemberReferences())
        {
            if (!(member.DeclaringType.Namespace.StartsWith("RoR2") || member.DeclaringType.Namespace.StartsWith("UnityEngine") || member.DeclaringType.Namespace.StartsWith("BepInEx") || member.DeclaringType.Namespace.StartsWith("R2API") || member.DeclaringType.Namespace.StartsWith("HarmonyLib"))) continue;
            if (member is MethodReference method) Check(method.Resolve() != null, "resolved API " + method.FullName);
            else if (member is FieldReference field) Check(field.Resolve() != null, "resolved API " + field.FullName);
            resolved++;
        }
        Console.WriteLine(JsonSerializer.Serialize(new { schema = 1, checksPassed = checks.Count, resolvedApiReferences = resolved, checks, assemblySha256 = Hash(built), runtimeVerified = false, clientMarkerDisplayVerified = false }, new JsonSerializerOptions { WriteIndented = true }));
    }
}
