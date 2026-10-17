using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

// Experimental transforms require exact source hash plus explicitly reviewed method/offsets.
// No transform suppresses Steam initialization failures or modifies network build identity.
internal static class Experimental
{
    internal static List<Action> Plan(AssemblyDefinition assembly, Manifest manifest)
    {
        var plans = new List<Action>();
        var methods = AllTypes(assembly.MainModule.Types).SelectMany(t => t.Methods).ToArray();
        MethodDefinition Method(string name) => methods.SingleOrDefault(m => m.FullName == name && m.HasBody)
            ?? throw new InvalidOperationException($"Missing exact method: {name}");
        if (manifest.ServerBootstrap is { } bootstrap)
            plans.AddRange(ServerBootstrap.Plan(assembly, bootstrap));
        if (manifest.Startup is { } startup)
        {
            var method = Method(startup.Method);
            if (method.DeclaringType.FullName != "RoR2.Console" || method.Name != "RunConfigsAfterLoad")
                throw new InvalidOperationException("Startup transform requires RoR2.Console.RunConfigsAfterLoad.");
            var anchor = At(method, startup.AfterCallOffset);
            var prefix = Previous(anchor, 4);
            bool instanceReceiver = method.HasThis && startup.ReceiverGetter == null && prefix[0].OpCode == OpCodes.Ldarg_0;
            bool getterReceiver = prefix[0].OpCode == OpCodes.Call && prefix[0].Operand is MethodReference getter && getter.FullName == startup.ReceiverGetter &&
                getter.Name == "get_instance" && !getter.HasThis && getter.Parameters.Count == 0 && getter.ReturnType.FullName == "RoR2.Console" && getter.DeclaringType.FullName == "RoR2.Console";
            if ((anchor.OpCode != OpCodes.Call && anchor.OpCode != OpCodes.Callvirt) || anchor.Operand is not MethodReference submit || submit.FullName != startup.SubmitCmd ||
                submit.Name != "SubmitCmd" || submit.DeclaringType.FullName != method.DeclaringType.FullName || !submit.HasThis || submit.ReturnType.MetadataType != MetadataType.Void || submit.Parameters.Count != 3 ||
                submit.Parameters[0].ParameterType.IsValueType || submit.Parameters[1].ParameterType.MetadataType != MetadataType.String || submit.Parameters[2].ParameterType.MetadataType != MetadataType.Boolean ||
                (!instanceReceiver && !getterReceiver) || prefix[1].OpCode != OpCodes.Ldnull || prefix[2].OpCode != OpCodes.Ldstr || prefix[2].Operand as string != "exec autoexec" || prefix[3].OpCode != OpCodes.Ldc_I4_0)
                throw new InvalidOperationException("Startup anchor must be the exact reviewed this.SubmitCmd(null, exec autoexec, false) sequence.");
            var collect = Method(startup.CollectHandlers);
            if (collect.DeclaringType.FullName != "RoR2.Networking.NetworkMessageHandlerAttribute" || collect.Name != "CollectHandlers" || collect.HasThis || collect.Parameters.Count != 0 || collect.ReturnType.MetadataType != MetadataType.Void)
                throw new InvalidOperationException("CollectHandlers must be static void RoR2.Networking.NetworkMessageHandlerAttribute.CollectHandlers().");
            if (method.Body.Instructions.Any(i => i.OpCode == OpCodes.Ldstr && i.Operand as string == "exec server_startup"))
                throw new InvalidOperationException("Startup command already exists; inspect the original assembly.");
            RequireLinear(method, prefix.Concat(new[] { anchor, anchor.Next ?? throw new InvalidOperationException("Startup anchor has no successor.") }).ToArray());
            plans.Add(() => {
                var il = method.Body.GetILProcessor();
                var cursor = anchor;
                var receiver = instanceReceiver ? il.Create(OpCodes.Ldarg_0) : il.Create(OpCodes.Call, (MethodReference)prefix[0].Operand);
                foreach (var item in new[] { il.Create(OpCodes.Call, collect), receiver, il.Create(OpCodes.Ldnull), il.Create(OpCodes.Ldstr, "exec server_startup"), il.Create(OpCodes.Ldc_I4_0), il.Create(anchor.OpCode, submit) })
                { il.InsertAfter(cursor, item); cursor = item; }
            });
        }
        if (manifest.Lobby is { } lobby)
        {
            var method = Method(lobby.Method);
            if (method.DeclaringType.FullName != "RoR2.SteamworksLobbyManager" || method.Name != "Init")
                throw new InvalidOperationException("Lobby transform requires RoR2.SteamworksLobbyManager.Init.");
            var start = At(method, lobby.Offset);
            var window = new[] { start, start.Next!, start.Next?.Next!, start.Next?.Next?.Next! };
            if (window.Any(i => i == null) || window[0].OpCode != OpCodes.Stloc_0 || window[1].OpCode != OpCodes.Ldarg_0 || window[2].OpCode != OpCodes.Ldloc_0 || window[3].OpCode != OpCodes.Newobj ||
                window[3].Operand is not MethodReference original || original.FullName != lobby.OriginalConstructor || original.Name != ".ctor" || original.Parameters.Count != 1 ||
                original.DeclaringType.FullName != "RoR2.LobbyManager/LobbyData")
                throw new InvalidOperationException("Lobby window differs from the reviewed stloc.0/ldarg.0/ldloc.0/newobj LobbyData sequence.");
            var replacement = methods.SingleOrDefault(m => m.FullName == lobby.NewConstructor && m.IsConstructor && !m.IsStatic && m.Parameters.Count == 0 && m.DeclaringType.FullName == original.DeclaringType.FullName)
                ?? throw new InvalidOperationException("Missing exact parameterless LobbyData constructor.");
            if (method.Body.Instructions.Any(i => i != window[2] && ReadsLocalZero(i)))
                throw new InvalidOperationException("Lobby setup local is used elsewhere; conversion would change semantics.");
            RequireLinear(method, window);
            plans.Add(() => { window[0].OpCode = OpCodes.Pop; window[0].Operand = null; window[2].OpCode = OpCodes.Nop; window[2].Operand = null; window[3].Operand = replacement; });
        }
        var appIds = manifest.AppIds ?? [];
        if (appIds.Select(s => (s.Method, s.Offset)).Distinct().Count() != appIds.Length) throw new InvalidOperationException("Duplicate AppID patch site.");
        foreach (var site in appIds)
        {
            var method = Method(site.Method);
            var instruction = At(method, site.Offset);
            if (site.From != 632360 || site.To != 1180760 || method.DeclaringType.FullName is not ("RoR2.SteamworksServerManager" or "RoR2.RoR2Application") ||
                instruction.OpCode != OpCodes.Ldc_I4 || instruction.Operand is not int value || value != site.From)
                throw new InvalidOperationException("AppID site must be a reviewed 632360-to-1180760 literal in SteamworksServerManager or RoR2Application.");
            plans.Add(() => instruction.Operand = site.To);
        }
        return plans;
    }
    private static bool ReadsLocalZero(Instruction i) => i.OpCode == OpCodes.Ldloc_0 || ((i.OpCode == OpCodes.Ldloc || i.OpCode == OpCodes.Ldloc_S || i.OpCode == OpCodes.Ldloca || i.OpCode == OpCodes.Ldloca_S) && i.Operand is VariableDefinition { Index: 0 });
    private static Instruction At(MethodDefinition method, int offset) => method.Body.Instructions.SingleOrDefault(i => i.Offset == offset) ?? throw new InvalidOperationException($"Offset {offset} is missing in {method.FullName}.");
    private static Instruction[] Previous(Instruction instruction, int count)
    {
        var previous = new List<Instruction>();
        var cursor = instruction;
        for (int i = 0; i < count; i++) { cursor = cursor.Previous ?? throw new InvalidOperationException("Truncated instruction window."); previous.Insert(0, cursor); }
        return previous.ToArray();
    }
    private static void RequireLinear(MethodDefinition method, Instruction[] window)
    {
        var targets = window.ToHashSet();
        foreach (var instruction in method.Body.Instructions)
            if ((instruction.Operand is Instruction target && targets.Contains(target)) || (instruction.Operand is Instruction[] branches && branches.Any(targets.Contains)))
                throw new InvalidOperationException("Reviewed window is a branch target; transformation rejected.");
        if (method.Body.ExceptionHandlers.Count != 0)
            throw new InvalidOperationException("Experimental startup/lobby transforms reject methods with exception handlers.");
    }
    private static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> types)
    {
        foreach (var type in types) { yield return type; foreach (var nested in AllTypes(type.NestedTypes)) yield return nested; }
    }
}
