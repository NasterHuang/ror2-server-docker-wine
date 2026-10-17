using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Reflection;
using BepInEx;
using RoR2;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;
using Path = System.IO.Path;
using R2API.Utils;
using HarmonyLib;

namespace Rains.ServerTools
{
    [BepInPlugin("local.rains.servertools", "Rains Server Tools", "0.1.0")]
    [BepInDependency("com.bepis.r2api", BepInDependency.DependencyFlags.HardDependency)]
    [NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)]
    public sealed class Plugin : BaseUnityPlugin
    {
        private readonly List<float> frames = new List<float>(4096);
        private string data;
        private float nextWrite, nextPoll, nextBoot;
        private float nextEntitySample;
        private string entitySampleJson;
        private DateTime bootStarted;
        private int mainThreadId;
        private int? initializationEnterState, initializationYieldState;
        private Harmony bootHarmony;
        private FieldInfo initializationStateField;
        private object contentIterator;
        private int? contentYieldState;
        private static Plugin bootObserver;
        private bool active, ready;
        private string lastAction = "none", lastResult = "none";
        private int errors;
        private Facepunch.Steamworks.ServerAuth observedAuth;
        private long steamAuthOkCallbacks, steamAuthFailureCallbacks;
        private Facepunch.Steamworks.Server observedServer;
        private long cmConnectedCallbacks, cmFailureCallbacks, cmDisconnectedCallbacks, cmDecodeErrors;
        private CmSample lastCm;

        private sealed class CmSample
        {
            public readonly string Event, Utc;
            public readonly int? Result;
            public readonly bool? StillRetrying;
            public CmSample(string name, int? result, bool? retry)
            {
                Event = name; Result = result; StillRetrying = retry;
                Utc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
            }
        }

        private void Awake()
        {
            active = Environment.GetEnvironmentVariable("RAINS_SERVER_TOOLS") == "1" && Application.isBatchMode;
            if (!active)
            {
                Logger.LogInfo("Server Tools disabled: requires RAINS_SERVER_TOOLS=1 and batchmode.");
                enabled = false;
                return;
            }
            // Wine maps the Unix root to Z:, whereas /data can resolve on C:.
            data = Environment.OSVersion.Platform == System.PlatformID.Win32NT ? @"Z:\data" : "/data";
            bootStarted = DateTime.UtcNow;
            mainThreadId = Thread.CurrentThread.ManagedThreadId;
            Logger.LogInfo("Server Tools enabled; game samples are not RTT, tickrate or multiplayer certification.");
            Guard(InstallBootObserver);
            Guard(WriteBootStatus);
        }

        private void Update()
        {
            if (!active) return;
            if (Time.realtimeSinceStartup >= nextBoot)
            {
                nextBoot = Time.realtimeSinceStartup + 5f;
                Guard(WriteBootStatus);
            }
            // Do not touch Steam singletons or catalogs during early plugin Awake.
            if (!RoR2Application.loadFinished) return;
            contentIterator = null;
            ObserveAuth();
            if (!ready) { ready = true; Logger.LogInfo("Game load finished; server observation active."); }
            if (frames.Count < 4096 && Time.unscaledDeltaTime >= 0)
                frames.Add(Time.unscaledDeltaTime * 1000f);
            float now = Time.realtimeSinceStartup;
            if (now >= nextPoll)
            {
                nextPoll = now + 0.5f;
                Guard(ConsumeRequest);
            }
            if (now >= nextWrite)
            {
                nextWrite = now + 5f;
                Guard(WriteStatus);
            }
        }

        private void ObserveAuth()
        {
            var server = Facepunch.Steamworks.Server.Instance;
            if (!ReferenceEquals(server, observedServer))
            {
                if (observedServer != null) observedServer.OnAnyCallback -= OnSteamCallback;
                observedServer = server;
                if (observedServer != null) observedServer.OnAnyCallback += OnSteamCallback;
            }
            var auth = server == null ? null : server.Auth;
            if (ReferenceEquals(auth, observedAuth)) return;
            if (observedAuth != null) observedAuth.OnAuthChange -= OnSteamAuthChange;
            observedAuth = auth;
            // Preserve the game's callback: its authentication/kick logic must run.
            if (observedAuth != null) observedAuth.OnAuthChange += OnSteamAuthChange;
        }

        private void OnSteamAuthChange(ulong unusedSteamId, ulong unusedOwnerId, Facepunch.Steamworks.ServerAuth.Status status)
        {
            // IDs deliberately never read, retained, serialized or logged.
            if (status == Facepunch.Steamworks.ServerAuth.Status.OK)
                Interlocked.Increment(ref steamAuthOkCallbacks);
            else if ((int)status >= 1 && (int)status <= 9)
                Interlocked.Increment(ref steamAuthFailureCallbacks);
        }

        private void OnDestroy()
        {
            if (ReferenceEquals(bootObserver, this)) bootObserver = null;
            if (bootHarmony != null) bootHarmony.UnpatchSelf();
            if (observedAuth != null) observedAuth.OnAuthChange -= OnSteamAuthChange;
            observedAuth = null;
            if (observedServer != null) observedServer.OnAnyCallback -= OnSteamCallback;
            observedServer = null;
        }

        private void OnSteamCallback(object callback)
        {
            // OnAnyCallback may carry private tickets/user data: never enumerate,
            // stringify or serialize its object. Only three exact SDK types qualify.
            try
            {
                if (callback == null) return;
                var type = callback.GetType();
                if (type.Assembly != typeof(Facepunch.Steamworks.Server).Assembly) return;
                string eventName;
                bool hasResult, hasRetry;
                switch (type.FullName)
                {
                    case "SteamNative.SteamServersConnected_t":
                        eventName = "connected"; hasResult = false; hasRetry = false;
                        Interlocked.Increment(ref cmConnectedCallbacks); break;
                    case "SteamNative.SteamServerConnectFailure_t":
                        eventName = "connect-failure"; hasResult = true; hasRetry = true;
                        Interlocked.Increment(ref cmFailureCallbacks); break;
                    case "SteamNative.SteamServersDisconnected_t":
                        eventName = "disconnected"; hasResult = true; hasRetry = false;
                        Interlocked.Increment(ref cmDisconnectedCallbacks); break;
                    default: return;
                }
                // SteamNative structs/fields are internal in this SDK; inspect only
                // the reviewed Result enum and StillRetrying boolean by exact name.
                const BindingFlags fields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                int? result = hasResult ? Convert.ToInt32(type.GetField("Result", fields).GetValue(callback), CultureInfo.InvariantCulture) : (int?)null;
                bool? retry = hasRetry ? (bool)type.GetField("StillRetrying", fields).GetValue(callback) : (bool?)null;
                Volatile.Write(ref lastCm, new CmSample(eventName, result, retry));
            }
            catch (Exception)
            {
                // Diagnostics must never disrupt the SDK/game callback chain.
                Interlocked.Increment(ref cmDecodeErrors);
            }
        }

        private void Guard(Action action)
        {
            try { action(); }
            catch (Exception ex)
            {
                // Avoid echoing user content or exception messages into logs.
                errors++;
                if (errors <= 3 || errors % 60 == 0)
                    Logger.LogWarning("Server Tools I/O/diagnostic error: " + ex.GetType().Name + " (count=" + errors + ")");
            }
        }

        private void ConsumeRequest()
        {
            string folder = Path.Combine(data, "admin");
            string request = Path.Combine(folder, "request.txt");
            if (!File.Exists(request)) return;
            string claimed = Path.Combine(folder, "processing-" + Guid.NewGuid().ToString("N") + ".txt");
            // Atomic claim: no automatic replay if the process dies afterwards.
            File.Move(request, claimed);
            try
            {
                string command;
                using (var input = new FileStream(claimed, FileMode.Open, FileAccess.Read, FileShare.None))
                {
                    if (input.Length > 128) { lastAction = "rejected"; lastResult = "request-too-long"; return; }
                    using (var reader = new StreamReader(input, Encoding.UTF8, true))
                        command = reader.ReadToEnd().Trim();
                }
                lastAction = command == "status" || command == "steam-info" || command == "start-run" ? command : "rejected";
                lastResult = "rejected";
                if (command == "status") lastResult = "sample-requested";
                else if (command == "steam-info")
                {
                    if (!RoR2.Console.instance) lastResult = "console-not-ready";
                    else
                    {
                        RoR2.Console.instance.SubmitCmd((NetworkUser)null, "steam_server_print_info", false);
                        lastResult = "submitted-see-local-game-log";
                    }
                }
                else if (command == "start-run")
                {
                    if (!NetworkServer.active || Run.instance || !PreGameController.instance ||
                        NetworkUser.readOnlyInstancesList.Count == 0 || !RoR2.Console.instance)
                        lastResult = "requires-active-server-pregame-player-and-no-run";
                    else
                    {
                        // Original command preserves game entitlement and BeginRun checks.
                        RoR2.Console.instance.SubmitCmd((NetworkUser)null, "pregame_start_run", false);
                        lastResult = "submitted-run-activation-not-yet-confirmed";
                    }
                }
                Logger.LogInfo("Server Tools action=" + lastAction + " result=" + lastResult);
                WriteStatus();
            }
            finally { File.Delete(claimed); }
        }

        private void WriteStatus()
        {
            // Admin status requests may arrive between scheduled writes. Reuse the
            // stamped sample so entity enumeration occurs at most once per 5s.
            float now = Time.realtimeSinceStartup;
            if (entitySampleJson == null || now >= nextEntitySample)
            {
                string sample = SampleRunAndBodies();
                entitySampleJson = sample;
                nextEntitySample = now + 5f;
            }
            var steam = Facepunch.Steamworks.Server.Instance;
            bool present = steam != null;
            var sorted = frames.ToArray();
            Array.Sort(sorted);
            double total = 0;
            foreach (float sample in sorted) total += sample;
            int count = sorted.Length;
            var json = new StringBuilder("{\n");
            Field(json, "schema", "1");
            Field(json, "sampleUtc", Quote(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)));
            Field(json, "gameLoadFinished", "true");
            Field(json, "clientWwiseCompatibility", Quote(ClientWwiseCompatibility.State));
            Field(json, "serverActive", Bool(NetworkServer.active));
            Field(json, "steamServerPresent", Bool(present));
            Field(json, "steamIsValid", Bool(present && steam.IsValid));
            Field(json, "steamLoggedOn", Bool(present && steam.LoggedOn));
            Field(json, "steamIdCachedNonzero", Bool(present && steam.SteamId != 0));
            Field(json, "steamAuthValidationOkCallbacks", Interlocked.Read(ref steamAuthOkCallbacks).ToString(CultureInfo.InvariantCulture));
            Field(json, "steamAuthValidationFailureCallbacks", Interlocked.Read(ref steamAuthFailureCallbacks).ToString(CultureInfo.InvariantCulture));
            Field(json, "steamCmConnectedCallbacks", Interlocked.Read(ref cmConnectedCallbacks).ToString(CultureInfo.InvariantCulture));
            Field(json, "steamCmConnectFailureCallbacks", Interlocked.Read(ref cmFailureCallbacks).ToString(CultureInfo.InvariantCulture));
            Field(json, "steamCmDisconnectedCallbacks", Interlocked.Read(ref cmDisconnectedCallbacks).ToString(CultureInfo.InvariantCulture));
            Field(json, "steamCmDecodeErrors", Interlocked.Read(ref cmDecodeErrors).ToString(CultureInfo.InvariantCulture));
            var cm = Volatile.Read(ref lastCm);
            Field(json, "steamCmLastEvent", cm == null ? "null" : Quote(cm.Event));
            Field(json, "steamCmLastEventUtc", cm == null ? "null" : Quote(cm.Utc));
            Field(json, "steamCmLastResultCode", cm == null || !cm.Result.HasValue ? "null" : cm.Result.Value.ToString(CultureInfo.InvariantCulture));
            Field(json, "steamCmLastStillRetrying", cm == null || !cm.StillRetrying.HasValue ? "null" : Bool(cm.StillRetrying.Value));
            Field(json, "networkUsers", NetworkUser.readOnlyInstancesList.Count.ToString(CultureInfo.InvariantCulture));
            Field(json, "runActive", Bool(Run.instance));
            json.Append(entitySampleJson);
            Field(json, "scene", Quote(SceneManager.GetActiveScene().name));
            Field(json, "targetFps", Application.targetFrameRate.ToString(CultureInfo.InvariantCulture));
            Field(json, "frameSamples", count.ToString(CultureInfo.InvariantCulture));
            Field(json, "frameIntervalMeanMs", Number(count == 0 ? 0 : total / count));
            Field(json, "frameIntervalP95Ms", Number(count == 0 ? 0 : sorted[(int)Math.Ceiling(count * .95) - 1]));
            Field(json, "frameIntervalMaxMs", Number(count == 0 ? 0 : sorted[count - 1]));
            Field(json, "lastAction", Quote(lastAction));
            Field(json, "lastActionResult", Quote(lastResult));
            json.Append("  \"measurementLimit\": \"Unity unscaled frame intervals; not CPU duration, network RTT, physics tickrate or authentication certification\"\n}\n");
            WriteJson("game.json", json.ToString());
            frames.Clear();
        }

        private static string SampleRunAndBodies()
        {
            // Called only from main-thread WriteStatus after loadFinished.
            // These are enabled CharacterBody components, not NetworkUser counts,
            // kills, living enemies, or evidence that a client received a spawn.
            var run = Run.instance;
            var bodies = CharacterBody.readOnlyInstancesList;
            int listCount = bodies.Count, total = 0, missing = 0;
            int controlled = 0, player = 0, monster = 0, lunar = 0, @void = 0;
            int cycle = 0, neutral = 0, other = 0, withoutTeam = 0;
            for (int i = 0; i < listCount; i++)
            {
                var body = bodies[i];
                if (!body) { missing++; continue; }
                total++;
                if (body.isPlayerControlled) controlled++;
                var team = body.teamComponent;
                if (!team) { withoutTeam++; continue; }
                switch (team.teamIndex)
                {
                    case TeamIndex.Player: player++; break;
                    case TeamIndex.Monster: monster++; break;
                    case TeamIndex.Lunar: lunar++; break;
                    case TeamIndex.Void: @void++; break;
                    case TeamIndex.EndOfTheCycle: cycle++; break;
                    case TeamIndex.Neutral: neutral++; break;
                    default: other++; break;
                }
            }
            var json = new StringBuilder();
            Field(json, "entitySampleUtc", Quote(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)));
            Field(json, "entitySampleRunActive", Bool(run));
            Field(json, "runStageClearCount", run ? run.stageClearCount.ToString(CultureInfo.InvariantCulture) : "null");
            Field(json, "runStopwatchSeconds", run ? Number(run.GetRunStopwatch()) : "null");
            Field(json, "characterBodyListCount", listCount.ToString(CultureInfo.InvariantCulture));
            Field(json, "characterBodies", total.ToString(CultureInfo.InvariantCulture));
            Field(json, "missingBodyReferences", missing.ToString(CultureInfo.InvariantCulture));
            Field(json, "playerControlledBodies", controlled.ToString(CultureInfo.InvariantCulture));
            Field(json, "playerTeamBodies", player.ToString(CultureInfo.InvariantCulture));
            Field(json, "monsterTeamBodies", monster.ToString(CultureInfo.InvariantCulture));
            Field(json, "lunarTeamBodies", lunar.ToString(CultureInfo.InvariantCulture));
            Field(json, "voidTeamBodies", @void.ToString(CultureInfo.InvariantCulture));
            Field(json, "endOfTheCycleTeamBodies", cycle.ToString(CultureInfo.InvariantCulture));
            Field(json, "neutralTeamBodies", neutral.ToString(CultureInfo.InvariantCulture));
            Field(json, "otherTeamBodies", other.ToString(CultureInfo.InvariantCulture));
            Field(json, "bodiesWithoutTeam", withoutTeam.ToString(CultureInfo.InvariantCulture));
            return json.ToString();
        }

        private void WriteBootStatus()
        {
            var json = new StringBuilder("{\n");
            Field(json, "schema", "1");
            Field(json, "sampleUtc", Quote(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)));
            Field(json, "elapsedSeconds", Number((DateTime.UtcNow - bootStarted).TotalSeconds));
            Field(json, "unityFrameCount", Time.frameCount.ToString(CultureInfo.InvariantCulture));
            Field(json, "gameLoadFinished", Bool(RoR2Application.loadFinished));
            Field(json, "clientWwiseCompatibility", Quote(ClientWwiseCompatibility.State));
            Field(json, "scene", Quote(SceneManager.GetActiveScene().name));
            Field(json, "initializationEnterState", initializationEnterState?.ToString(CultureInfo.InvariantCulture) ?? "null");
            Field(json, "initializationYieldState", initializationYieldState?.ToString(CultureInfo.InvariantCulture) ?? "null");
            Field(json, "contentYieldState", contentYieldState?.ToString(CultureInfo.InvariantCulture) ?? "null");
            if (contentIterator != null)
            {
                const BindingFlags instanceFields = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
                var stack = contentIterator.GetType().GetField("<coroutineStack>5__8", instanceFields)?.GetValue(contentIterator);
                var collection = stack as ICollection;
                Field(json, "contentCoroutineStackCount", collection == null ? "null" : collection.Count.ToString(CultureInfo.InvariantCulture));
                object top = collection != null && collection.Count > 0 ? stack.GetType().GetMethod("Peek").Invoke(stack, null) : null;
                Field(json, "contentTopCoroutineType", top == null ? "null" : Quote(top.GetType().FullName));
                object topState = top?.GetType().GetField("<>1__state", instanceFields)?.GetValue(top);
                Field(json, "contentTopCoroutineState", topState is int ? ((int)topState).ToString(CultureInfo.InvariantCulture) : "null");
            }
            // Reviewed 25921972 .cctor only initializes a bool, a List<Type>,
            // and the constant 22ms budget. Never invoke ExecuteStatic/Coroutine,
            // enumerate the queue, or write these fields. They may change mid-sample.
            const BindingFlags flags = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
            var type = typeof(SystemInitializerAttribute);
            var executed = type.GetField("hasExecuted", flags);
            var thread = type.GetField("initThread", flags)?.GetValue(null) as Thread;
            var queue = type.GetField("initializerAttributes", flags)?.GetValue(null) as ICollection;
            var budget = type.GetField("FRAME_TIME_THRESHOLD_MS", flags)?.GetValue(null);
            Field(json, "initializersExecuted", executed == null ? "null" : Bool((bool)executed.GetValue(null)));
            Field(json, "initializerThreadAlive", thread == null ? "null" : Bool(thread.IsAlive));
            Field(json, "initializerQueueCount", queue == null ? "null" : queue.Count.ToString(CultureInfo.InvariantCulture));
            Field(json, "initializerFrameBudgetMs", budget == null ? "null" : Convert.ToInt64(budget, CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture));
            json.Append("  \"measurementLimit\": \"Main-thread observation; a blocked main thread stops updates. No initialization or readiness is forced.\"\n}\n");
            WriteJson("boot.json", json.ToString());
        }

        private void InstallBootObserver()
        {
            // Exact reviewed compiler-generated type for build 25921972. Observers
            // return void, never change fields/results, and never catch game exceptions.
            var type = typeof(RoR2Application).GetNestedType("<InitializeGameRoutine>d__114", BindingFlags.NonPublic);
            if (type == null) throw new MissingMemberException();
            initializationStateField = type.GetField("<>1__state", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (initializationStateField == null) throw new MissingFieldException();
            var step = type.GetMethod("MoveNext", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (step == null) throw new MissingMethodException();
            bootObserver = this;
            bootHarmony = new Harmony("local.rains.servertools.boot-observer");
            bootHarmony.Patch(step,
                prefix: new HarmonyMethod(typeof(Plugin).GetMethod(nameof(BeforeInitializationStep), BindingFlags.Static | BindingFlags.NonPublic)),
                postfix: new HarmonyMethod(typeof(Plugin).GetMethod(nameof(AfterInitializationStep), BindingFlags.Static | BindingFlags.NonPublic)));
            var contentType = typeof(RoR2Application).GetNestedType("<LoadGameContent>d__115", BindingFlags.NonPublic);
            var contentStep = contentType?.GetMethod("MoveNext", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (contentStep == null) throw new MissingMethodException();
            bootHarmony.Patch(contentStep, postfix: new HarmonyMethod(typeof(Plugin).GetMethod(nameof(AfterContentStep), BindingFlags.Static | BindingFlags.NonPublic)));
        }

        private static void BeforeInitializationStep(object __instance)
        {
            var observer = bootObserver;
            if (observer == null || Thread.CurrentThread.ManagedThreadId != observer.mainThreadId) return;
            observer.Guard(() =>
            {
                observer.initializationEnterState = (int)observer.initializationStateField.GetValue(__instance);
                observer.WriteBootStatus();
            });
        }

        private static void AfterInitializationStep(object __instance)
        {
            var observer = bootObserver;
            if (observer == null || Thread.CurrentThread.ManagedThreadId != observer.mainThreadId) return;
            observer.Guard(() =>
            {
                observer.initializationYieldState = (int)observer.initializationStateField.GetValue(__instance);
                observer.WriteBootStatus();
            });
        }

        private static void AfterContentStep(object __instance)
        {
            var observer = bootObserver;
            if (observer == null || Thread.CurrentThread.ManagedThreadId != observer.mainThreadId) return;
            // Only retain the startup iterator and read its numeric state. Periodic
            // Update samples it; no file writes or queue enumeration on each frame.
            observer.Guard(() =>
            {
                observer.contentIterator = __instance;
                var field = __instance.GetType().GetField("<>1__state", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
                observer.contentYieldState = field == null ? (int?)null : (int)field.GetValue(__instance);
            });
        }

        private void WriteJson(string name, string content)
        {
            string folder = Path.Combine(data, "status");
            Directory.CreateDirectory(folder);
            string destination = Path.Combine(folder, name);
            string temporary = Path.Combine(folder, "game-" + Guid.NewGuid().ToString("N") + ".tmp");
            try
            {
                File.WriteAllText(temporary, content, new UTF8Encoding(false));
                if (File.Exists(destination)) File.Replace(temporary, destination, null);
                else File.Move(temporary, destination);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }

        private static string Bool(bool value) { return value ? "true" : "false"; }
        private static string Number(double value) { return double.IsNaN(value) || double.IsInfinity(value) ? "null" : value.ToString("0.###", CultureInfo.InvariantCulture); }
        private static void Field(StringBuilder output, string name, string value) { output.Append("  ").Append(Quote(name)).Append(": ").Append(value).Append(",\n"); }
        private static string Quote(string text)
        {
            var result = new StringBuilder("\"");
            foreach (char c in text ?? "")
                if (c == '"' || c == '\\') result.Append('\\').Append(c);
                else if (c < 32) result.Append("\\u").Append(((int)c).ToString("x4"));
                else result.Append(c);
            return result.Append('"').ToString();
        }
    }
}
