using System.Security.Cryptography;
using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;
using RoR2DedicatedPatcher;

string work = Path.Combine(Path.GetTempPath(), "ror2-patcher-tests-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(work);
string input = Path.Combine(work, "RoR2.dll"), output = Path.Combine(work, "patched.dll"), manifest = Path.Combine(work, "manifest.json"), report = Path.Combine(work, "report.json");
int passed = 0;
void Check(bool condition, string name) { if (!condition) throw new Exception(name); Console.WriteLine("PASS " + name); passed++; }
int Run(params string[] args) => RoR2DedicatedPatcher.Program.Main(args);
try
{
    using (var a = AssemblyDefinition.CreateAssembly(new AssemblyNameDefinition("RoR2", new Version(1, 0)), "RoR2", ModuleKind.Dll))
    {
        var module = a.MainModule;
        TypeDefinition Type(string ns, string name) { var t = new TypeDefinition(ns, name, TypeAttributes.Public | TypeAttributes.Class, module.TypeSystem.Object); module.Types.Add(t); return t; }
        MethodDefinition Method(TypeDefinition t, string name, bool instance = false) { var m = new MethodDefinition(name, MethodAttributes.Public | (instance ? 0 : MethodAttributes.Static), module.TypeSystem.Void); t.Methods.Add(m); return m; }
        var server = Type("RoR2", "SteamworksServerManager");
        var setter = Method(server, "set_DedicatedServer", true); setter.Parameters.Add(new ParameterDefinition(module.TypeSystem.Boolean)); setter.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var init = Method(server, "Initialize", true); var il = init.Body.Instructions;
        il.Add(Instruction.Create(OpCodes.Ldarg_0)); il.Add(Instruction.Create(OpCodes.Ldc_I4_0)); il.Add(Instruction.Create(OpCodes.Callvirt, setter)); il.Add(Instruction.Create(OpCodes.Ret));
        var console = Type("RoR2", "Console"); var submit = Method(console, "SubmitCmd", true);
        submit.Parameters.Add(new ParameterDefinition(module.TypeSystem.Object)); submit.Parameters.Add(new ParameterDefinition(module.TypeSystem.String)); submit.Parameters.Add(new ParameterDefinition(module.TypeSystem.Boolean)); submit.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var startup = Method(console, "RunConfigsAfterLoad", true); il = startup.Body.Instructions;
        il.Add(Instruction.Create(OpCodes.Ldarg_0)); il.Add(Instruction.Create(OpCodes.Ldnull)); il.Add(Instruction.Create(OpCodes.Ldstr, "exec autoexec")); il.Add(Instruction.Create(OpCodes.Ldc_I4_0)); il.Add(Instruction.Create(OpCodes.Call, submit)); il.Add(Instruction.Create(OpCodes.Ret));
        var handlers = Type("RoR2.Networking", "NetworkMessageHandlerAttribute"); Method(handlers, "CollectHandlers").Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var lobby = Type("RoR2", "LobbyManager"); var data = new TypeDefinition("", "LobbyData", TypeAttributes.NestedPublic | TypeAttributes.Class, module.TypeSystem.Object); lobby.NestedTypes.Add(data);
        var ctor = Method(data, ".ctor", true); ctor.Attributes |= MethodAttributes.SpecialName | MethodAttributes.RTSpecialName; ctor.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var ctor1 = Method(data, ".ctor", true); ctor1.Attributes |= MethodAttributes.SpecialName | MethodAttributes.RTSpecialName; ctor1.Parameters.Add(new ParameterDefinition(module.TypeSystem.String)); ctor1.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var lobbyManager = Type("RoR2", "SteamworksLobbyManager"); var lobbyInit = Method(lobbyManager, "Init", true); lobbyInit.Body.Variables.Add(new VariableDefinition(module.TypeSystem.String)); il = lobbyInit.Body.Instructions;
        il.Add(Instruction.Create(OpCodes.Ldnull)); il.Add(Instruction.Create(OpCodes.Stloc_0)); il.Add(Instruction.Create(OpCodes.Ldarg_0)); il.Add(Instruction.Create(OpCodes.Ldloc_0)); il.Add(Instruction.Create(OpCodes.Newobj, ctor1)); il.Add(Instruction.Create(OpCodes.Pop)); il.Add(Instruction.Create(OpCodes.Pop)); il.Add(Instruction.Create(OpCodes.Ret));
        var app = Type("RoR2", "RoR2Application"); var appMethod = Method(app, "InitSteam"); appMethod.Body.Instructions.Add(Instruction.Create(OpCodes.Ldc_I4, 632360)); appMethod.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); appMethod.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var build = Method(app, "AssignBuildId"); build.Body.Instructions.Add(Instruction.Create(OpCodes.Ldstr, "real-build")); build.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); build.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var platformSystems = Type("RoR2", "PlatformSystems"); platformSystems.Fields.Add(new FieldDefinition("lobbyManager", FieldAttributes.Public | FieldAttributes.Static, lobby));
        var userManager = Type("RoR2", "UserManager"); var steamUserManager = Type("RoR2", "SteamUserManager"); steamUserManager.BaseType = userManager;
        var dummyUserManager = Type("RoR2", "UserManagerDummy"); dummyUserManager.BaseType = userManager;
        var steamUserCtor = Method(steamUserManager, ".ctor", true); steamUserCtor.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        Method(dummyUserManager, ".ctor", true).Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var initSteamUser = Method(steamUserManager, "InitializeUserManager", true); initSteamUser.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var userField = new FieldDefinition("userManager", FieldAttributes.Public | FieldAttributes.Static, userManager); platformSystems.Fields.Add(userField);
        var initPlatform = Method(platformSystems, "Init"); il = initPlatform.Body.Instructions; var callInitSteam = Instruction.Create(OpCodes.Call, initSteamUser); var platformRet = Instruction.Create(OpCodes.Ret);
        il.Add(Instruction.Create(OpCodes.Newobj, steamUserCtor)); il.Add(Instruction.Create(OpCodes.Stsfld, userField)); il.Add(Instruction.Create(OpCodes.Ldsfld, userField)); il.Add(Instruction.Create(OpCodes.Isinst, steamUserManager)); il.Add(Instruction.Create(OpCodes.Dup)); il.Add(Instruction.Create(OpCodes.Brtrue_S, callInitSteam)); il.Add(Instruction.Create(OpCodes.Pop)); il.Add(Instruction.Create(OpCodes.Br_S, platformRet)); il.Add(callInitSteam); il.Add(platformRet);
        var setData = Method(lobby, "set_newestLobbyData", true); setData.Parameters.Add(new ParameterDefinition(data)); setData.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var clientManager = Type("RoR2", "SteamworksClientManager"); var clientCtor = Method(clientManager, ".ctor", true); clientCtor.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var closure = new TypeDefinition("", "<>c", TypeAttributes.NestedPublic | TypeAttributes.Class, module.TypeSystem.Object); clientManager.NestedTypes.Add(closure);
        var loader = Method(closure, "<Init>b__12_0", true); loader.ReturnType = module.TypeSystem.Boolean; loader.Body.Instructions.Add(Instruction.Create(OpCodes.Newobj, clientCtor)); loader.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); loader.Body.Instructions.Add(Instruction.Create(OpCodes.Ldc_I4_0)); loader.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        Method(closure, "<Init>b__12_1", true).Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var refs = Method(app, "BootstrapReferences");
        var generic = new GenericInstanceType(new TypeReference("RoR2", "ServerManagerBase`1", module, module)); generic.GenericArguments.Add(server);
        var nativeServer = new TypeReference("Facepunch.Steamworks", "Server", module, module);
        var nativeBase = new TypeReference("Facepunch.Steamworks", "BaseSteamworks", module, module);
        var runtimePlatform = new TypeReference("UnityEngine", "RuntimePlatform", module, module, true);
        var application = new TypeReference("UnityEngine", "Application", module, module);
        var config = new TypeReference("Facepunch.Steamworks", "Config", module, module);
        MethodReference Ref(TypeReference type, string name, TypeReference returns, bool instance = false) => new MethodReference(name, returns, type) { HasThis = instance };
        foreach (var reference in new[] { Ref(generic, "StartServer", module.TypeSystem.Void), Ref(generic, "StopServer", module.TypeSystem.Void), Ref(nativeServer, "get_Instance", nativeServer), Ref(application, "get_platform", runtimePlatform) })
        { refs.Body.Instructions.Add(Instruction.Create(OpCodes.Call, reference)); if (reference.ReturnType.MetadataType != MetadataType.Void) refs.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); }
        refs.Body.Instructions.Add(Instruction.Create(OpCodes.Ldnull)); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Callvirt, Ref(nativeBase, "get_IsValid", module.TypeSystem.Boolean, true))); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Pop));
        refs.Body.Instructions.Add(Instruction.Create(OpCodes.Ldnull)); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Callvirt, Ref(module.TypeSystem.Object, "ToString", module.TypeSystem.String, true))); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Pop));
        var forUnity = Ref(config, "ForUnity", module.TypeSystem.Void); forUnity.Parameters.Add(new ParameterDefinition(module.TypeSystem.String)); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Ldstr, "Synthetic")); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Call, forUnity)); refs.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var idReference = Method(app, "ServerIdReference"); idReference.Body.Instructions.Add(Instruction.Create(OpCodes.Ldnull)); idReference.Body.Instructions.Add(Instruction.Create(OpCodes.Callvirt, Ref(nativeServer, "get_SteamId", module.TypeSystem.UInt64, true))); idReference.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); idReference.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var nativeClient = new TypeReference("Facepunch.Steamworks", "Client", module, module);
        var clientGetter = Ref(nativeClient, "get_Instance", nativeClient);
        var networkManager = Type("RoR2.Networking", "NetworkManagerSystemSteam");
        var updateServer = Method(networkManager, "UpdateServer", true); for (int n = 0; n < 48; n++) updateServer.Body.Instructions.Add(Instruction.Create(OpCodes.Nop));
        updateServer.Body.Instructions.Add(Instruction.Create(OpCodes.Call, clientGetter)); updateServer.Body.Instructions.Add(Instruction.Create(OpCodes.Callvirt, Ref(nativeBase, "get_Networking", new TypeReference("Facepunch.Steamworks", "Networking", module, module), true))); updateServer.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); updateServer.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        foreach (string name in new[] { "ForceCloseAllConnections", "CheckSteamworks" }) { var m = Method(networkManager, name, name != "CheckSteamworks"); m.Body.Instructions.Add(Instruction.Create(OpCodes.Call, clientGetter)); m.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); m.Body.Instructions.Add(Instruction.Create(OpCodes.Ret)); }
        var getClient = Method(networkManager, "GetClient", true); getClient.ReturnType = new TypeReference("UnityEngine.Networking", "NetworkConnection", module, module); getClient.Parameters.Add(new ParameterDefinition(new TypeReference("RoR2", "PlatformID", module, module, true)));
        for (int n = 0; n < 15; n++) getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Nop)); getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Call, clientGetter)); getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Callvirt, Ref(nativeClient, "get_SteamId", module.TypeSystem.UInt64, true))); getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Pop)); getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Ldnull)); getClient.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var initP2P = Method(networkManager, "InitP2P", true); initP2P.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var initPlatformServer = Method(networkManager, "InitPlatformServer", true); initPlatformServer.Body.Instructions.Add(Instruction.Create(OpCodes.Call, Ref(generic, "StartServer", module.TypeSystem.Void))); initPlatformServer.Body.Instructions.Add(Instruction.Create(OpCodes.Ldarg_0)); initPlatformServer.Body.Instructions.Add(Instruction.Create(OpCodes.Call, initP2P)); initPlatformServer.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var routineType = new TypeDefinition("", "<InitializeGameRoutine>d__114", TypeAttributes.NestedPublic | TypeAttributes.Class, module.TypeSystem.Object); app.NestedTypes.Add(routineType);
        var routine = Method(routineType, "MoveNext", true); routine.ReturnType = module.TypeSystem.Boolean; routine.Body.Variables.Add(new VariableDefinition(module.TypeSystem.Object)); routine.Body.Variables.Add(new VariableDefinition(app));
        var func = new GenericInstanceType(new TypeReference("System", "Func`1", module, module.TypeSystem.Object.Scope)); func.GenericArguments.Add(module.TypeSystem.Boolean);
        var loadField = new FieldDefinition("loadSteamworksClient", FieldAttributes.Public | FieldAttributes.Static, func); var failedField = new FieldDefinition("steamworksFailed", FieldAttributes.Public, module.TypeSystem.Boolean); app.Fields.Add(loadField); app.Fields.Add(failedField);
        var rewired = Type("RoR2", "RewiredIntegrationManager"); var rewiredInit = Method(rewired, "Init"); rewiredInit.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        il = routine.Body.Instructions; for (int n = 0; n < 787; n++) il.Add(Instruction.Create(OpCodes.Nop));
        var invoke = Instruction.Create(OpCodes.Callvirt, Ref(func, "Invoke", module.TypeSystem.Boolean, true)); var branchToNext = Instruction.Create(OpCodes.Brtrue_S, Instruction.Create(OpCodes.Nop)); var resume = Instruction.Create(OpCodes.Call, rewiredInit); branchToNext.Operand = resume;
        il.Add(Instruction.Create(OpCodes.Ldsfld, loadField)); il.Add(Instruction.Create(OpCodes.Dup)); il.Add(Instruction.Create(OpCodes.Brtrue_S, invoke)); il.Add(Instruction.Create(OpCodes.Pop)); il.Add(Instruction.Create(OpCodes.Ldc_I4_0)); il.Add(Instruction.Create(OpCodes.Br_S, branchToNext)); il.Add(invoke); il.Add(branchToNext); il.Add(Instruction.Create(OpCodes.Ldloc_1)); il.Add(Instruction.Create(OpCodes.Ldc_I4_1)); il.Add(Instruction.Create(OpCodes.Stfld, failedField)); il.Add(resume); il.Add(Instruction.Create(OpCodes.Ldc_I4_0)); il.Add(Instruction.Create(OpCodes.Ret));
        a.Write(input);
    }
    string hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(input))).ToLowerInvariant();
    object approved;
    using (var fixture = AssemblyDefinition.ReadAssembly(input))
    {
        var types = fixture.MainModule.Types;
        var server = types.Single(t => t.Name == "SteamworksServerManager");
        var console = types.Single(t => t.Name == "Console"); var startup = console.Methods.Single(m => m.Name == "RunConfigsAfterLoad");
        var data = types.Single(t => t.Name == "LobbyManager").NestedTypes.Single();
        var lobby = types.Single(t => t.Name == "SteamworksLobbyManager").Methods.Single();
        var app = types.Single(t => t.Name == "RoR2Application").Methods.Single(m => m.Name == "InitSteam");
        approved = new { inputSha256 = hash,
            patches = new[] { new { method = server.Methods.Single(m => m.Name == "Initialize").FullName, offset = 1, setter = server.Methods.Single(m => m.Name.StartsWith("set_")).FullName } },
            startup = new { method = startup.FullName, afterCallOffset = startup.Body.Instructions.Single(i => i.OpCode == OpCodes.Call).Offset, submitCmd = console.Methods.Single(m => m.Name == "SubmitCmd").FullName, collectHandlers = types.Single(t => t.Name == "NetworkMessageHandlerAttribute").Methods.Single().FullName },
            lobby = new { method = lobby.FullName, offset = lobby.Body.Instructions[1].Offset, originalConstructor = data.Methods.Single(m => m.Parameters.Count == 1).FullName, newConstructor = data.Methods.Single(m => m.Parameters.Count == 0).FullName },
            appIds = new[] { new { method = app.FullName, offset = 0, from = 632360, to = 1180760 } },
            serverBootstrap = new { loaderMethod = "System.Boolean RoR2.SteamworksClientManager/<>c::<Init>b__12_0()", unloaderMethod = "System.Void RoR2.SteamworksClientManager/<>c::<Init>b__12_1()", useDummyUserManager = true, useServerNetworking = true }
        };
    }
    string manifestJson = JsonSerializer.Serialize(approved); File.WriteAllText(manifest, manifestJson);
    Check(Run("--inspect", "--input", input, "--report", report) == 0, "inspect succeeds");
    Check(File.ReadAllText(report).Contains("real-build"), "audit includes actual build assignment");
    Check(Run("--input", input, "--output", output, "--manifest", manifest, "--report", report) == 0, "full experimental profile applies");
    byte[] patched = File.ReadAllBytes(output);
    using (var result = AssemblyDefinition.ReadAssembly(output))
    {
        var methods = result.MainModule.Types.SelectMany(t => t.Methods).ToArray();
        Check(methods.Single(m => m.Name == "Initialize").Body.Instructions[1].OpCode == OpCodes.Ldc_I4_1, "dedicated flag enabled");
        var startup = methods.Single(m => m.Name == "RunConfigsAfterLoad").Body.Instructions;
        Check(startup.Any(i => i.OpCode == OpCodes.Ldstr && i.Operand as string == "exec server_startup"), "startup command injected");
        Check(startup[5].OpCode == OpCodes.Call && ((MethodReference)startup[5].Operand).Name == "CollectHandlers", "handlers injected before startup");
        Check(methods.Single(m => m.DeclaringType.Name == "SteamworksLobbyManager").Body.Instructions[1].OpCode == OpCodes.Pop, "lobby preserves producer stack with pop");
        Check((int)methods.Single(m => m.Name == "InitSteam").Body.Instructions[0].Operand == 1180760, "scoped AppID converted");
        Check(methods.Single(m => m.Name == "AssignBuildId").Body.Instructions[0].Operand as string == "real-build", "build identity unchanged");
        var loaders = result.MainModule.Types.Single(t => t.Name == "SteamworksClientManager").NestedTypes.Single().Methods;
        var serverLoader = loaders.Single(m => m.Name == "<Init>b__12_0").Body.Instructions;
        Check(serverLoader.Any(i => i.Operand is MethodReference r && r.Name == "StartServer"), "bootstrap calls real server initialization");
        Check(serverLoader.Any(i => i.Operand is MethodReference r && r.Name == "get_IsValid") && !serverLoader.Any(i => i.OpCode == OpCodes.Ldc_I4_1), "bootstrap reads real validity rather than unconditional success");
        Check(serverLoader.Any(i => i.OpCode == OpCodes.Ldc_I4_0), "missing server returns failure");
        Check(loaders.Single(m => m.Name == "<Init>b__12_1").Body.Instructions.Any(i => i.Operand is MethodReference r && r.Name == "StopServer"), "shutdown disposes real server");
        Check(methods.Single(m => m.DeclaringType.Name == "PlatformSystems" && m.Name == "Init").Body.Instructions[0].Operand is MethodReference dummy && dummy.DeclaringType.Name == "UserManagerDummy", "bootstrap reuses built-in dummy user service");
        Check(methods.Where(m => m.DeclaringType.Name == "NetworkManagerSystemSteam").SelectMany(m => m.Body.Instructions).Where(i => i.Operand is MethodReference r && r.Name == "get_Instance").All(i => ((MethodReference)i.Operand).DeclaringType.FullName == "Facepunch.Steamworks.Server"), "server-only network paths use real server singleton");
        Check(methods.Single(m => m.Name == "GetClient").Body.Instructions.Any(i => i.Operand is MethodReference r && r.Name == "get_SteamId" && r.DeclaringType.FullName == "Facepunch.Steamworks.Server"), "paired server SteamId consumer preserves receiver type");
    }
    Check(Run("--input", input, "--output", output, "--manifest", manifest, "--report", report) == 0 && File.ReadAllBytes(output).SequenceEqual(patched), "repeat from original is byte-idempotent");
    Check(File.ReadAllText(report).Contains("unchanged"), "repeat reports unchanged");
    var deferredManifest = System.Text.Json.Nodes.JsonNode.Parse(manifestJson)!; deferredManifest["serverBootstrap"]!["deferUntilHost"] = true; File.WriteAllText(manifest, deferredManifest.ToJsonString());
    string deferredOutput = Path.Combine(work, "deferred.dll");
    Check(Run("--input", input, "--output", deferredOutput, "--manifest", manifest, "--report", report) == 0, "deferred profile applies");
    using (var result = AssemblyDefinition.ReadAssembly(deferredOutput))
    {
        var routine = result.MainModule.Types.Single(t => t.Name == "RoR2Application").NestedTypes.Single().Methods.Single();
        Check(routine.Body.Instructions.Any(i => i.OpCode == OpCodes.Br && i.Operand is Instruction target && target.Operand is MethodReference r && r.DeclaringType.Name == "RewiredIntegrationManager"), "deferred mode skips the complete client-only block");
        var bypass = routine.Body.Instructions.Single(i => i.OpCode == OpCodes.Br && i.Operand is Instruction target && target.Operand is MethodReference r && r.DeclaringType.Name == "RewiredIntegrationManager");
        var skipped = routine.Body.Instructions.Skip(routine.Body.Instructions.IndexOf(bypass) + 1).TakeWhile(i => i != bypass.Operand).ToArray();
        Check(skipped.Length == 10 && skipped.All(i => i.OpCode == OpCodes.Nop && i.Operand == null), "discarded client block contains no orphaned stack consumers");
        Check(routine.Body.Instructions.Where(i => i.OpCode.FlowControl is FlowControl.Branch or FlowControl.Cond_Branch).All(i => i.OpCode.OperandType != OperandType.ShortInlineBrTarget), "modified coroutine branches cannot overflow short offsets");
        Check(routine.Body.Instructions.Any(i => i.Operand is MethodReference r && r.Name == "ForUnity") && !routine.Body.Instructions.Any(i => i.Operand is MethodReference r && r.Name == "StartServer"), "early stage configures native platform without creating server");
        var host = result.MainModule.Types.Single(t => t.Name == "NetworkManagerSystemSteam").Methods.Single(m => m.Name == "InitPlatformServer");
        Check(host.Body.Instructions.Count(i => i.OpCode == OpCodes.Throw) == 2 && host.Body.Instructions.Any(i => i.Operand is MethodReference r && r.Name == "get_IsValid"), "host stage propagates missing or invalid real server");
    }
    byte[] deferredBytes = File.ReadAllBytes(deferredOutput);
    Check(Run("--input", input, "--output", deferredOutput, "--manifest", manifest, "--report", report) == 0 && File.ReadAllBytes(deferredOutput).SequenceEqual(deferredBytes), "deferred repeat remains byte-idempotent");
    File.WriteAllText(manifest, manifestJson.Replace(hash, new string('0', 64)));
    Check(Run("--input", input, "--output", output, "--manifest", manifest) != 0 && File.ReadAllBytes(output).SequenceEqual(patched), "source drift leaves existing output intact");
    File.WriteAllText(manifest, manifestJson.Replace("exec", "exec" ).Replace("CollectHandlers()", "MissingHandlers()"));
    Check(Run("--input", input, "--output", output, "--manifest", manifest) != 0 && File.ReadAllBytes(output).SequenceEqual(patched), "missing optional target cancels entire write");
    File.WriteAllText(manifest, manifestJson);
    Check(Run("--input", output, "--output", Path.Combine(work, "twice.dll"), "--manifest", manifest) != 0, "patched input rejected by hash pin");
    Check(Run("--input", input, "--output", input, "--manifest", manifest) != 0, "in-place writes refused");
    Check(Run("--inspect", "--input", input, "--report", input) != 0, "report cannot overwrite input");
    Check(Run("--input") != 0 && Run("--wat") != 0, "invalid CLI fails");
    Check(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(input))).ToLowerInvariant() == hash, "original remains unchanged");
    Console.WriteLine($"{passed} checks passed. Synthetic assemblies only; no actual game execution.");
}
finally { Directory.Delete(work, true); }
