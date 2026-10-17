using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

// An opt-in server loader, never a claim that a complete standalone platform is verified.
// The original failure flag consumes the real server SDK's IsValid result.
internal static class ServerBootstrap
{
    internal static List<Action> Plan(AssemblyDefinition assembly, BootstrapSite site)
    {
        var all = AllTypes(assembly.MainModule.Types).SelectMany(t => t.Methods).ToArray();
        var loader = all.SingleOrDefault(m => m.FullName == site.LoaderMethod && m.HasBody);
        var unloader = all.SingleOrDefault(m => m.FullName == site.UnloaderMethod && m.HasBody);
        if (loader == null || unloader == null || loader.DeclaringType.FullName != "RoR2.SteamworksClientManager/<>c" || loader.Name != "<Init>b__12_0" ||
            unloader.DeclaringType.FullName != loader.DeclaringType.FullName || unloader.Name != "<Init>b__12_1" || loader.ReturnType.MetadataType != MetadataType.Boolean ||
            unloader.ReturnType.MetadataType != MetadataType.Void || loader.Parameters.Count != 0 || unloader.Parameters.Count != 0 ||
            loader.Body.Instructions[0].OpCode != OpCodes.Newobj || loader.Body.Instructions[0].Operand is not MethodReference originalCtor || originalCtor.FullName != "System.Void RoR2.SteamworksClientManager::.ctor()")
            throw new InvalidOperationException("Server bootstrap requires the exact reviewed current-build client loader/unloader delegates.");
        var references = all.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions).Select(i => i.Operand).OfType<MethodReference>().ToArray();
        MethodReference Reference(string name) => references.FirstOrDefault(r => r.FullName == name) ?? throw new InvalidOperationException($"Server bootstrap reference missing: {name}");
        var start = Reference("System.Void RoR2.ServerManagerBase`1<RoR2.SteamworksServerManager>::StartServer()");
        var stop = Reference("System.Void RoR2.ServerManagerBase`1<RoR2.SteamworksServerManager>::StopServer()");
        var instance = Reference("Facepunch.Steamworks.Server Facepunch.Steamworks.Server::get_Instance()");
        var valid = Reference("System.Boolean Facepunch.Steamworks.BaseSteamworks::get_IsValid()");
        var platform = Reference("UnityEngine.RuntimePlatform UnityEngine.Application::get_platform()");
        var stringify = Reference("System.String System.Object::ToString()");
        var configure = Reference("System.Void Facepunch.Steamworks.Config::ForUnity(System.String)");
        var lobby = assembly.MainModule.Types.Single(t => t.FullName == "RoR2.PlatformSystems").Fields.Single(f => f.FullName == "RoR2.LobbyManager RoR2.PlatformSystems::lobbyManager");
        var data = all.Single(m => m.FullName == "System.Void RoR2.LobbyManager/LobbyData::.ctor()");
        var setData = all.Single(m => m.FullName == "System.Void RoR2.LobbyManager::set_newestLobbyData(RoR2.LobbyManager/LobbyData)");
        var changes = new List<Action>();
        if (site.UseServerNetworking) changes.AddRange(ServerNetworking.Plan(all));
        if (site.UseDummyUserManager)
        {
            var init = all.Single(m => m.FullName == "System.Void RoR2.PlatformSystems::Init()");
            var constructorSites = init.Body.Instructions.Where(i => i.OpCode == OpCodes.Newobj && i.Operand is MethodReference constructor && constructor.FullName == "System.Void RoR2.SteamUserManager::.ctor()").ToArray();
            var dummyConstructor = all.Single(m => m.FullName == "System.Void RoR2.UserManagerDummy::.ctor()");
            if (constructorSites.Length != 1 || constructorSites[0].Next?.OpCode != OpCodes.Stsfld || constructorSites[0].Next?.Operand is not FieldReference userField || userField.FullName != "RoR2.UserManager RoR2.PlatformSystems::userManager")
                throw new InvalidOperationException("Missing exact SteamUserManager platform constructor/store window.");
            var typeCheck = constructorSites[0].Next?.Next?.Next;
            if (typeCheck?.OpCode != OpCodes.Isinst || typeCheck.Operand is not TypeReference checkedType || checkedType.FullName != "RoR2.SteamUserManager" ||
                typeCheck.Next?.OpCode != OpCodes.Dup || typeCheck.Next.Next?.OpCode != OpCodes.Brtrue_S || typeCheck.Next.Next.Next?.OpCode != OpCodes.Pop)
                throw new InvalidOperationException("Expected guarded SteamUserManager-specific initialization after construction.");
            changes.Add(() => constructorSites[0].Operand = dummyConstructor);
        }
        if (site.DeferUntilHost)
        {
            changes.AddRange(DeferredServer.Plan(all));
            changes.Add(() => {
                unloader.Body = new MethodBody(unloader);
                unloader.Body.Instructions.Add(Instruction.Create(OpCodes.Call, stop));
                unloader.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
            });
            return changes;
        }
        changes.Add(() => {
            loader.Body = new MethodBody(loader);
            var il = loader.Body.GetILProcessor();
            var hasServer = il.Create(OpCodes.Callvirt, valid);
            il.Append(il.Create(OpCodes.Call, platform));
            il.Append(il.Create(OpCodes.Box, platform.ReturnType));
            il.Append(il.Create(OpCodes.Callvirt, stringify));
            il.Append(il.Create(OpCodes.Call, configure));
            il.Append(il.Create(OpCodes.Ldsfld, lobby));
            il.Append(il.Create(OpCodes.Newobj, data));
            il.Append(il.Create(OpCodes.Callvirt, setData));
            il.Append(il.Create(OpCodes.Call, start));
            il.Append(il.Create(OpCodes.Call, instance));
            il.Append(il.Create(OpCodes.Dup));
            il.Append(il.Create(OpCodes.Brtrue, hasServer));
            il.Append(il.Create(OpCodes.Pop));
            il.Append(il.Create(OpCodes.Ldc_I4_0));
            il.Append(il.Create(OpCodes.Ret));
            il.Append(hasServer);
            il.Append(il.Create(OpCodes.Ret));
            unloader.Body = new MethodBody(unloader);
            unloader.Body.Instructions.Add(Instruction.Create(OpCodes.Call, stop));
            unloader.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        });
        return changes;
    }
    private static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> types)
    {
        foreach (var type in types) { yield return type; foreach (var nested in AllTypes(type.NestedTypes)) yield return nested; }
    }
}
