using System.Security.Cryptography;
using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;

namespace RoR2DedicatedPatcher;

internal sealed record PatchSite(string Method, int Offset, string Setter);
internal sealed record StartupSite(string Method, int AfterCallOffset, string SubmitCmd, string CollectHandlers, string? ReceiverGetter = null);
internal sealed record LobbySite(string Method, int Offset, string OriginalConstructor, string NewConstructor);
internal sealed record AppIdSite(string Method, int Offset, int From, int To);
internal sealed record BootstrapSite(string LoaderMethod, string UnloaderMethod, bool UseDummyUserManager = false, bool UseServerNetworking = false, bool DeferUntilHost = false);
internal sealed record Manifest(string InputSha256, PatchSite[] Patches, StartupSite? Startup = null, LobbySite? Lobby = null, AppIdSite[]? AppIds = null, BootstrapSite? ServerBootstrap = null);

public static class Program
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true, UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };
    private static readonly string[] RelevantTypes = ["SteamworksServerManager", "RoR2Application", "Console", "SteamworksLobbyManager", "LobbyManager", "LobbyData", "NetworkMessageHandlerAttribute", "ServerAuthManager", "PlatformSystems", "SteamworksClientManager", "NetworkManagerSystemSteam", "SteamUserManager", "SaveSystemSteam", "AchievementSystemSteam", "SteamworksEntitlementResolver"];

    public static int Main(string[] args)
    {
        var report = new Dictionary<string, object?> { ["status"] = "failed", ["gameRuntimeVerified"] = false };
        string? reportPath = null;
        try
        {
            var options = Parse(args);
            if (options.ContainsKey("help"))
            {
                Console.WriteLine("RoR2Patcher --inspect --input RoR2.dll [--report audit.json]\nRoR2Patcher --input RoR2.dll --output RoR2.patched.dll --manifest approved.json [--report result.json]\nOnly an explicitly approved, SHA256-pinned DedicatedServer false-to-true change is supported. No game-version compatibility is implied.");
                return 0;
            }
            reportPath = options.GetValueOrDefault("report");
            string input = Path.GetFullPath(Required(options, "input"));
            byte[] source = File.ReadAllBytes(input);
            string sourceHash = Hash(source);
            report["input"] = input;
            report["sourceSha256"] = sourceHash;
            using var resolver = new DefaultAssemblyResolver();
            resolver.AddSearchDirectory(Path.GetDirectoryName(input)!);
            using var assembly = AssemblyDefinition.ReadAssembly(new MemoryStream(source), new ReaderParameters { AssemblyResolver = resolver, InMemory = true });
            if (assembly.Name.Name != "RoR2") throw new InvalidOperationException("Expected an assembly named RoR2.");
            if (assembly.Name.HasPublicKey) throw new InvalidOperationException("Strong-named inputs require a separately reviewed signing strategy.");
            report["assembly"] = assembly.Name.FullName;
            report["moduleMvid"] = assembly.MainModule.Mvid;
            report["audit"] = Audit(assembly);
            report["steamClientDependencies"] = Types(assembly.MainModule.Types).SelectMany(t => t.Methods).Where(m => m.HasBody)
                .SelectMany(m => m.Body.Instructions.Where(i => i.Operand is MethodReference reference && reference.DeclaringType.FullName == "Facepunch.Steamworks.Client" && reference.Name == "get_Instance")
                    .Select(i => new { method = m.FullName, offset = i.Offset })).ToArray();
            if (reportPath != null && string.Equals(Path.GetFullPath(reportPath), input, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Report must not overwrite the input assembly.");
            if (options.ContainsKey("inspect"))
            {
                if (options.ContainsKey("output") || options.ContainsKey("manifest")) throw new ArgumentException("--inspect cannot be combined with --output or --manifest.");
                report["status"] = "inspected";
                report["patches"] = Array.Empty<object>();
                WriteReport(reportPath, report);
                return 0;
            }
            string output = Path.GetFullPath(Required(options, "output"));
            if (string.Equals(input, output, OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
                throw new ArgumentException("Input and output must differ; preserve the original game assembly.");
            if (reportPath != null && new[] { input, output }.Any(p => string.Equals(Path.GetFullPath(reportPath), p, StringComparison.OrdinalIgnoreCase)))
                throw new ArgumentException("Report must not overwrite an input or output assembly.");
            var manifest = JsonSerializer.Deserialize<Manifest>(File.ReadAllText(Required(options, "manifest")), Json) ?? throw new ArgumentException("Empty manifest.");
            if (!string.Equals(manifest.InputSha256, sourceHash, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Input SHA256 differs from the reviewed manifest. Inspect and review this exact game build first.");
            if (manifest.Patches is not { Length: 1 }) throw new ArgumentException("Exactly one reviewed DedicatedServer patch site is required.");
            var site = manifest.Patches[0];
            var matches = Types(assembly.MainModule.Types).SelectMany(t => t.Methods).Where(m => m.FullName == site.Method).ToArray();
            if (matches.Length != 1 || !matches[0].HasBody) throw new InvalidOperationException("Reviewed method is missing or ambiguous.");
            var method = matches[0];
            if (method.DeclaringType.FullName != "RoR2.SteamworksServerManager") throw new InvalidOperationException("Only RoR2.SteamworksServerManager can be patched.");
            var instructions = method.Body.Instructions;
            var targets = instructions.Where(i => i.Offset == site.Offset).ToArray();
            if (targets.Length != 1) throw new InvalidOperationException("Reviewed instruction offset is missing or ambiguous.");
            var value = targets[0];
            var call = value.Next;
            if (value.OpCode != OpCodes.Ldc_I4_0 || call == null || (call.OpCode != OpCodes.Callvirt && call.OpCode != OpCodes.Call) ||
                call.Operand is not MethodReference setter || setter.FullName != site.Setter || !setter.HasThis || setter.Name != "set_DedicatedServer" ||
                setter.ReturnType.MetadataType != MetadataType.Void || setter.Parameters.Count != 1 || setter.Parameters[0].ParameterType.MetadataType != MetadataType.Boolean)
                throw new InvalidOperationException("Reviewed site is not an instance void set_DedicatedServer(bool) preceded by ldc.i4.0.");
            // All optional transforms are planned first; one failed precondition cancels the whole write.
            var optionalChanges = Experimental.Plan(assembly, manifest);
            var changedMethodNames = manifest.Patches.Select(p => p.Method)
                .Concat(manifest.Startup == null ? [] : new[] { manifest.Startup.Method })
                .Concat(manifest.Lobby == null ? [] : new[] { manifest.Lobby.Method })
                .Concat((manifest.AppIds ?? []).Select(p => p.Method))
                .Concat(manifest.ServerBootstrap == null ? [] : manifest.ServerBootstrap.DeferUntilHost ? new[] { manifest.ServerBootstrap.UnloaderMethod }.Concat(DeferredServer.MethodNames) : new[] { manifest.ServerBootstrap.LoaderMethod, manifest.ServerBootstrap.UnloaderMethod })
                .Concat(manifest.ServerBootstrap?.UseDummyUserManager == true ? new[] { "System.Void RoR2.PlatformSystems::Init()" } : [])
                .Concat(manifest.ServerBootstrap?.UseServerNetworking == true ? ServerNetworking.MethodNames : [])
                .Distinct(StringComparer.Ordinal).ToArray();
            // Modify the existing object in place. Branch and exception-handler targets remain valid;
            // both opcodes have identical stack effects and encoded size.
            value.OpCode = OpCodes.Ldc_I4_1;
            foreach (var change in optionalChanges) change();
            foreach (var changedMethodName in changedMethodNames)
                ILSafety.NormalizeAndVerify(Types(assembly.MainModule.Types).SelectMany(t => t.Methods).Single(m => m.FullName == changedMethodName));
            using var buffer = new MemoryStream();
            assembly.Write(buffer);
            byte[] patched = buffer.ToArray();
            // Re-read before writing so serialization errors never damage an existing output.
            using (var verification = AssemblyDefinition.ReadAssembly(new MemoryStream(patched)))
            {
                var verifiedMethod = Types(verification.MainModule.Types).SelectMany(t => t.Methods).Single(m => m.FullName == site.Method);
                if (verifiedMethod.Body.Instructions.Single(i => i.Offset == value.Offset).OpCode != OpCodes.Ldc_I4_1)
                    throw new InvalidOperationException("Serialized patch verification failed.");
                foreach (var changedMethodName in changedMethodNames)
                {
                    var expected = Types(assembly.MainModule.Types).SelectMany(t => t.Methods).Single(m => m.FullName == changedMethodName);
                    var actual = Types(verification.MainModule.Types).SelectMany(t => t.Methods).Single(m => m.FullName == changedMethodName);
                    if (!expected.Body.Instructions.Select(i => i.ToString()).SequenceEqual(actual.Body.Instructions.Select(i => i.ToString())))
                        throw new InvalidOperationException($"Serialized transform differs: {changedMethodName}");
                }
            }
            Directory.CreateDirectory(Path.GetDirectoryName(output)!);
            bool unchanged = File.Exists(output) && File.ReadAllBytes(output).AsSpan().SequenceEqual(patched);
            if (!unchanged) AtomicWrite(output, patched);
            report["output"] = output;
            report["outputSha256"] = Hash(patched);
            report["patches"] = manifest.Patches;
            report["experimental"] = new { manifest.Startup, manifest.Lobby, manifest.AppIds, manifest.ServerBootstrap };
            report["changedMethods"] = changedMethodNames;
            report["status"] = unchanged ? "unchanged" : "patched";
            WriteReport(reportPath, report);
            return 0;
        }
        catch (Exception error)
        {
            report.Remove("audit");
            report.Remove("steamClientDependencies");
            report["error"] = error.Message;
            // Never write a failure report to a user-controlled path before safe-path validation.
            Console.Error.WriteLine(JsonSerializer.Serialize(report, Json));
            return 1;
        }
    }

    private static object[] Audit(AssemblyDefinition assembly) => Types(assembly.MainModule.Types)
        .Where(t => RelevantTypes.Contains(t.Name) || t.FullName.StartsWith("RoR2.SteamworksClientManager/", StringComparison.Ordinal) || t.FullName.Contains("InitializeGameRoutine", StringComparison.Ordinal))
        .Select(t => (object)new { type = t.FullName, methods = t.Methods.Where(m => m.HasBody).Select(m => new {
            method = m.FullName,
            instructions = m.Body.Instructions.Select(i => new { offset = i.Offset, opcode = i.OpCode.Name, operand = i.Operand?.ToString() }).ToArray()
        }).ToArray() }).ToArray();

    private static IEnumerable<TypeDefinition> Types(IEnumerable<TypeDefinition> roots)
    {
        foreach (var type in roots) { yield return type; foreach (var child in Types(type.NestedTypes)) yield return child; }
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string Required(Dictionary<string, string> options, string name) => options.GetValueOrDefault(name) ?? throw new ArgumentException($"Missing --{name}.");
    private static Dictionary<string, string> Parse(string[] args)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        for (int i = 0; i < args.Length; i++)
        {
            string key = args[i] switch { "-i" => "input", "-o" => "output", "-h" => "help", _ when args[i].StartsWith("--", StringComparison.Ordinal) => args[i][2..], _ => throw new ArgumentException($"Unknown argument {args[i]}.") };
            if (key is not ("input" or "output" or "manifest" or "report" or "inspect" or "help")) throw new ArgumentException($"Unknown option --{key}.");
            if (result.ContainsKey(key)) throw new ArgumentException($"Duplicate --{key}.");
            if (key is "inspect" or "help") result[key] = "true";
            else if (++i >= args.Length || args[i].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException($"Missing value for --{key}.");
            else result[key] = args[i];
        }
        return result;
    }
    private static void WriteReport(string? path, Dictionary<string, object?> report)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(report, Json);
        if (path == null) Console.WriteLine(System.Text.Encoding.UTF8.GetString(bytes));
        else { string full = Path.GetFullPath(path); Directory.CreateDirectory(Path.GetDirectoryName(full)!); AtomicWrite(full, bytes); }
    }
    private static void AtomicWrite(string path, byte[] bytes)
    {
        string temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllBytes(temporary, bytes); File.Move(temporary, path, true); }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
