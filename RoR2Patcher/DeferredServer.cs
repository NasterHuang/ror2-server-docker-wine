using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

// Client bootstrap is inapplicable in this explicitly selected dedicated profile.
// Skip that complete block, then let the ordinary post-catalog host path initialize
// the real server. Never write steamworksFailed=false or fabricate loader success.
internal static class DeferredServer
{
    internal static readonly string[] MethodNames = [
        "System.Boolean RoR2.RoR2Application/<InitializeGameRoutine>d__114::MoveNext()",
        "System.Void RoR2.Networking.NetworkManagerSystemSteam::InitPlatformServer()"
    ];
    internal static List<Action> Plan(MethodDefinition[] all)
    {
        var routine = all.Single(m => m.FullName == MethodNames[0] && m.HasBody);
        var first = routine.Body.Instructions.Single(i => i.Offset == 787);
        var resume = routine.Body.Instructions.Single(i => i.Offset == 813);
        var window = routine.Body.Instructions.Where(i => i.Offset >= 787 && i.Offset < 813).ToArray();
        Code[] expected = [Code.Ldsfld, Code.Dup, Code.Brtrue_S, Code.Pop, Code.Ldc_I4_0, Code.Br_S, Code.Callvirt, Code.Brtrue_S, Code.Ldloc_1, Code.Ldc_I4_1, Code.Stfld];
        if (!window.Select(i => i.OpCode.Code).SequenceEqual(expected) || first.Operand is not FieldReference source || source.FullName != "System.Func`1<System.Boolean> RoR2.RoR2Application::loadSteamworksClient" ||
            window[^1].Operand is not FieldReference failed || failed.FullName != "System.Boolean RoR2.RoR2Application::steamworksFailed" ||
            resume.Operand is not MethodReference next || next.FullName != "System.Void RoR2.RewiredIntegrationManager::Init()")
            throw new InvalidOperationException("Deferred-server client-only coroutine window differs from reviewed current build.");
        var windowSet = window.ToHashSet();
        foreach (var instruction in routine.Body.Instructions.Where(i => !windowSet.Contains(i)))
            if ((instruction.Operand is Instruction target && windowSet.Contains(target)) || (instruction.Operand is Instruction[] targets && targets.Any(windowSet.Contains)))
                throw new InvalidOperationException("External branch enters the client-only block; cannot safely bypass it.");
        foreach (var handler in routine.Body.ExceptionHandlers)
        {
            bool Within(Instruction instruction, Instruction? start, Instruction? end) => start != null && instruction.Offset >= start.Offset && (end == null || instruction.Offset < end.Offset);
            if (Within(first, handler.TryStart, handler.TryEnd) != Within(resume, handler.TryStart, handler.TryEnd) ||
                Within(first, handler.HandlerStart, handler.HandlerEnd) != Within(resume, handler.HandlerStart, handler.HandlerEnd) ||
                (handler.FilterStart != null && Within(first, handler.FilterStart, handler.HandlerStart) != Within(resume, handler.FilterStart, handler.HandlerStart)))
                throw new InvalidOperationException("Deferred-server branch would cross an exception-handler boundary.");
        }
        var module = routine.Module;
        var lobby = module.Types.Single(t => t.FullName == "RoR2.PlatformSystems").Fields.Single(f => f.FullName == "RoR2.LobbyManager RoR2.PlatformSystems::lobbyManager");
        var data = all.Single(m => m.FullName == "System.Void RoR2.LobbyManager/LobbyData::.ctor()");
        var setData = all.Single(m => m.FullName == "System.Void RoR2.LobbyManager::set_newestLobbyData(RoR2.LobbyManager/LobbyData)");
        var host = all.Single(m => m.FullName == MethodNames[1] && m.HasBody);
        var body = host.Body.Instructions;
        if (body.Count != 4 || body[0].OpCode != OpCodes.Call || body[0].Operand is not MethodReference startServer || startServer.FullName != "System.Void RoR2.ServerManagerBase`1<RoR2.SteamworksServerManager>::StartServer()" ||
            body[1].OpCode != OpCodes.Ldarg_0 || body[2].OpCode != OpCodes.Call || body[2].Operand is not MethodReference initP2P || initP2P.FullName != "System.Void RoR2.Networking.NetworkManagerSystemSteam::InitP2P()" || body[3].OpCode != OpCodes.Ret || host.Body.ExceptionHandlers.Count != 0)
            throw new InvalidOperationException("Deferred-server host initialization is not the exact reviewed StartServer/InitP2P sequence.");
        var references = all.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions).Select(i => i.Operand).OfType<MethodReference>().ToArray();
        var server = references.First(m => m.FullName == "Facepunch.Steamworks.Server Facepunch.Steamworks.Server::get_Instance()");
        var valid = references.First(m => m.FullName == "System.Boolean Facepunch.Steamworks.BaseSteamworks::get_IsValid()");
        var platform = references.First(m => m.FullName == "UnityEngine.RuntimePlatform UnityEngine.Application::get_platform()");
        var stringify = references.First(m => m.FullName == "System.String System.Object::ToString()");
        var configure = references.First(m => m.FullName == "System.Void Facepunch.Steamworks.Config::ForUnity(System.String)");
        // Reference the game's existing mscorlib, never the patcher's .NET runtime.
        var exceptionType = new TypeReference("System", "InvalidOperationException", module, module.TypeSystem.Object.Scope);
        var exceptionConstructor = new MethodReference(".ctor", module.TypeSystem.Void, exceptionType) { HasThis = true };
        exceptionConstructor.Parameters.Add(new ParameterDefinition(module.TypeSystem.String));
        return [() => {
            var il = routine.Body.GetILProcessor();
            il.InsertBefore(first, il.Create(OpCodes.Call, platform));
            il.InsertBefore(first, il.Create(OpCodes.Box, platform.ReturnType));
            il.InsertBefore(first, il.Create(OpCodes.Callvirt, stringify));
            il.InsertBefore(first, il.Create(OpCodes.Call, configure));
            il.InsertBefore(first, il.Create(OpCodes.Ldsfld, lobby));
            il.InsertBefore(first, il.Create(OpCodes.Newobj, data));
            il.InsertBefore(first, il.Create(OpCodes.Callvirt, setData));
            first.OpCode = OpCodes.Br; first.Operand = resume;
            // Mono validates otherwise-unreachable IL too. Do not leave the original
            // dup/call/stfld consumers behind after removing their initial load.
            foreach (var discarded in window.Skip(1)) { discarded.OpCode = OpCodes.Nop; discarded.Operand = null; }
            host.Body = new MethodBody(host);
            il = host.Body.GetILProcessor();
            var check = il.Create(OpCodes.Callvirt, valid);
            var proceed = il.Create(OpCodes.Ldarg_0);
            il.Append(il.Create(OpCodes.Call, startServer));
            il.Append(il.Create(OpCodes.Call, server));
            il.Append(il.Create(OpCodes.Dup));
            il.Append(il.Create(OpCodes.Brtrue, check));
            il.Append(il.Create(OpCodes.Pop));
            il.Append(il.Create(OpCodes.Ldstr, "Dedicated Steam server initialization produced no server instance."));
            il.Append(il.Create(OpCodes.Newobj, exceptionConstructor)); il.Append(il.Create(OpCodes.Throw));
            il.Append(check); il.Append(il.Create(OpCodes.Brtrue, proceed));
            il.Append(il.Create(OpCodes.Ldstr, "Dedicated Steam server initialization failed: IsValid is false."));
            il.Append(il.Create(OpCodes.Newobj, exceptionConstructor)); il.Append(il.Create(OpCodes.Throw));
            il.Append(proceed); il.Append(il.Create(OpCodes.Call, initP2P)); il.Append(il.Create(OpCodes.Ret));
        }];
    }
}
