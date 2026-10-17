using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

// Current-build, server-only reference substitutions. All stack consumers retain their
// original signatures; no authentication, version comparison or timeout is bypassed.
internal static class ServerNetworking
{
    internal static readonly string[] MethodNames = [
        "System.Void RoR2.Networking.NetworkManagerSystemSteam::UpdateServer()",
        "System.Void RoR2.Networking.NetworkManagerSystemSteam::ForceCloseAllConnections()",
        "System.Void RoR2.Networking.NetworkManagerSystemSteam::CheckSteamworks()",
        "UnityEngine.Networking.NetworkConnection RoR2.Networking.NetworkManagerSystemSteam::GetClient(RoR2.PlatformID)"
    ];
    private const string ClientGetter = "Facepunch.Steamworks.Client Facepunch.Steamworks.Client::get_Instance()";
    private const string ServerGetter = "Facepunch.Steamworks.Server Facepunch.Steamworks.Server::get_Instance()";
    private const string ClientId = "System.UInt64 Facepunch.Steamworks.Client::get_SteamId()";
    private const string ServerId = "System.UInt64 Facepunch.Steamworks.Server::get_SteamId()";

    internal static List<Action> Plan(MethodDefinition[] all)
    {
        var refs = all.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions).Select(i => i.Operand).OfType<MethodReference>().ToArray();
        var serverGetter = refs.FirstOrDefault(m => m.FullName == ServerGetter && !m.HasThis && m.Parameters.Count == 0)
            ?? throw new InvalidOperationException("Missing existing server singleton getter.");
        var serverId = refs.FirstOrDefault(m => m.FullName == ServerId && m.HasThis && m.Parameters.Count == 0)
            ?? throw new InvalidOperationException("Missing existing server SteamId getter.");
        var replacements = new List<Action>();
        var offsets = new[] { 48, 0, 0, 15 };
        for (int n = 0; n < MethodNames.Length; n++)
        {
            var method = all.Single(m => m.FullName == MethodNames[n] && m.HasBody);
            var calls = method.Body.Instructions.Where(i => i.Operand is MethodReference m && m.FullName == ClientGetter).ToArray();
            if (calls.Length != 1 || calls[0].Offset != offsets[n] || calls[0].OpCode != OpCodes.Call)
                throw new InvalidOperationException($"Server networking getter window drifted: {method.FullName}");
            var instruction = calls[0];
            if (n == 0 && (instruction.Next?.Operand is not MethodReference networking || networking.FullName != "Facepunch.Steamworks.Networking Facepunch.Steamworks.BaseSteamworks::get_Networking()"))
                throw new InvalidOperationException("UpdateServer receiver is not consumed by the shared BaseSteamworks networking getter.");
            if (n == 3)
            {
                var idInstruction = instruction.Next;
                if (idInstruction?.OpCode != OpCodes.Callvirt || idInstruction.Operand is not MethodReference original || original.FullName != ClientId)
                    throw new InvalidOperationException("GetClient SteamId consumer differs from the reviewed paired replacement.");
                replacements.Add(() => idInstruction.Operand = serverId);
            }
            replacements.Add(() => instruction.Operand = serverGetter);
        }
        return replacements;
    }
}
