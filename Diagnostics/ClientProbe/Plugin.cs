using System;
using System.Globalization;
using System.IO;
using System.Text;
using BepInEx;
using R2API.Utils;
using RoR2;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;
using Path = System.IO.Path;

namespace Rains.ClientProbe
{
    [BepInPlugin("local.rains.clientprobe", "Rains Client Probe", "0.1.0")]
    [BepInDependency("com.bepis.r2api", BepInDependency.DependencyFlags.HardDependency)]
    [NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)]
    public sealed class Plugin : BaseUnityPlugin
    {
        private string output;
        private float nextSample;
        private bool announced;

        private void Awake()
        {
            if (Environment.GetEnvironmentVariable("RAINS_CLIENT_PROBE") != "1" || !Application.isBatchMode)
            {
                enabled = false;
                return;
            }
            try
            {
                output = LocalDirectory(Environment.GetEnvironmentVariable("RAINS_CLIENT_PROBE_DIR"));
                Directory.CreateDirectory(output);
                Logger.LogInfo("Read-only batch client probe enabled; no authentication or game state is changed.");
            }
            catch (Exception error)
            {
                Logger.LogError("Client probe disabled: output directory unavailable or not an absolute local directory (" + error.GetType().Name + ").");
                enabled = false;
            }
        }

        private static string LocalDirectory(string directory)
        {
            if (string.IsNullOrWhiteSpace(directory) || !Path.IsPathFullyQualified(directory) ||
                directory.StartsWith(@"\\", StringComparison.Ordinal) || directory.StartsWith("//", StringComparison.Ordinal))
                throw new ArgumentException();
            string full = Path.GetFullPath(directory);
            if (Environment.OSVersion.Platform == System.PlatformID.Win32NT)
            {
                // A mapped network drive is also remote even when it has a drive letter.
                var drive = new DriveInfo(Path.GetPathRoot(full));
                if (drive.DriveType == DriveType.Network || drive.DriveType == DriveType.Unknown || drive.DriveType == DriveType.NoRootDirectory)
                    throw new ArgumentException();
            }
            return full;
        }

        private void Update()
        {
            if (!RoR2Application.loadFinished || Time.realtimeSinceStartup < nextSample) return;
            nextSample = Time.realtimeSinceStartup + 5f;
            try
            {
                WriteSample();
                if (!announced)
                {
                    announced = true;
                    Logger.LogInfo("Client probe wrote its first loaded-game sample.");
                }
            }
            catch (Exception error)
            {
                // Do not serialize exception contents, which can include paths or private connection data.
                Logger.LogWarning("Client probe sample failed (" + error.GetType().Name + ").");
            }
        }

        private void WriteSample()
        {
            int bodies = 0, playerBodies = 0, monsterBodies = 0;
            // Called on Unity's main thread, once per five seconds after loadFinished.
            foreach (CharacterBody body in CharacterBody.readOnlyInstancesList)
            {
                if (!body) continue;
                bodies++;
                if (body.isPlayerControlled) playerBodies++;
                if (body.teamComponent && body.teamComponent.teamIndex == TeamIndex.Monster) monsterBodies++;
            }
            var run = Run.instance;
            string json = "{\n" +
                "  \"schema\": 1,\n" +
                "  \"sampleUtc\": " + Quote(DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture)) + ",\n" +
                "  \"gameLoadFinished\": true,\n" +
                "  \"scene\": " + Quote(SceneManager.GetActiveScene().name) + ",\n" +
                "  \"clientActive\": " + Bool(NetworkClient.active) + ",\n" +
                "  \"clientSceneReady\": " + Bool(ClientScene.ready) + ",\n" +
                "  \"networkUsers\": " + Integer(NetworkUser.readOnlyInstancesList.Count) + ",\n" +
                "  \"runActive\": " + Bool(run) + ",\n" +
                "  \"stageClearCount\": " + (run ? Integer(run.stageClearCount) : "null") + ",\n" +
                "  \"runStopwatchSeconds\": " + (run ? Number(run.GetRunStopwatch()) : "null") + ",\n" +
                "  \"characterBodies\": " + Integer(bodies) + ",\n" +
                "  \"playerControlledBodies\": " + Integer(playerBodies) + ",\n" +
                "  \"monsterBodies\": " + Integer(monsterBodies) + ",\n" +
                "  \"measurementLimit\": \"Client-side replicated-object counts in batchmode; not visual playability, RTT, packet loss or multiplayer stability certification.\"\n" +
                "}\n";
            string destination = Path.Combine(output, "game.json");
            string temporary = Path.Combine(output, "game.json.tmp");
            File.WriteAllText(temporary, json, new UTF8Encoding(false));
            if (File.Exists(destination)) File.Replace(temporary, destination, null);
            else File.Move(temporary, destination);
        }

        private static string Bool(bool value) => value ? "true" : "false";
        private static string Integer(int value) => value.ToString(CultureInfo.InvariantCulture);
        private static string Number(float value) => float.IsNaN(value) || float.IsInfinity(value) ? "null" : value.ToString("R", CultureInfo.InvariantCulture);
        private static string Quote(string value)
        {
            var result = new StringBuilder("\"");
            foreach (char character in value ?? "")
            {
                if (character == '"' || character == '\\') result.Append('\\').Append(character);
                else if (character < 0x20) result.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                else result.Append(character);
            }
            return result.Append('"').ToString();
        }
    }
}
