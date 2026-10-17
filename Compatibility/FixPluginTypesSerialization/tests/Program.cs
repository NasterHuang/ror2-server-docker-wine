using System;using System.IO;using System.Reflection;using System.Runtime.InteropServices;using System.Runtime.Loader;using System.Linq;
class Program {
static void Check(bool yes,string name){if(!yes)throw new Exception(name);Console.WriteLine("PASS "+name);}
static byte[] Read(IntPtr p,int n){var b=new byte[n];Marshal.Copy(p,b,0,n);return b;}
static void Main(string[] args){if(args.Length!=2)throw new ArgumentException("Expected candidate DLL and BepInEx/core directory");AssemblyLoadContext.Default.Resolving+=(context,name)=>{var p=Path.GetFullPath(Path.Combine(args[1],name.Name+".dll"));return File.Exists(p)?context.LoadFromAssemblyPath(p):null;};
var a=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(args[0]));
var common=a.GetType("FixPluginTypesSerialization.Util.CommonUnityFunctions",true);var field=common.GetField("<ScriptingAssemblies>k__BackingField",BindingFlags.Static|BindingFlags.NonPublic);
var manager=a.GetType("FixPluginTypesSerialization.UnityPlayer.Structs.v2021.v1.MonoManager",true);
var global=Marshal.AllocHGlobal(256);var state=Marshal.AllocHGlobal(64);Marshal.Copy(new byte[256],0,global,256);Marshal.Copy(new byte[64],0,state,64);Marshal.WriteIntPtr(global,state);field.SetValue(null,global);
try {Marshal.WriteIntPtr(state,new IntPtr(0x1111));Marshal.WriteInt32(state,8,42);Marshal.WriteIntPtr(state,32,new IntPtr(0x2222));var oldNames=Read(state,32);var instance=Activator.CreateInstance(manager);
manager.GetMethod("CopyNativeAssemblyListToManaged").Invoke(instance,null);
bool rejected=false;try{manager.GetMethod("CopyNativeAssemblyListToManaged").Invoke(instance,null);}catch(TargetInvocationException e){rejected=e.InnerException is InvalidOperationException;}Check(rejected,"repeat injection rejected before native vector replacement");
Marshal.WriteIntPtr(state,new IntPtr(0x3333));Marshal.WriteInt64(state,16,2);Marshal.WriteInt64(state,24,2);Marshal.WriteIntPtr(state,32,new IntPtr(0x4444));Marshal.WriteInt32(state,40,55);Marshal.WriteInt64(state,48,8);var updatedTypes=Read(state+32,32);
manager.GetMethod("RestoreOriginalAssemblyNamesArrayPtr").Invoke(instance,null);Check(Read(state,32).SequenceEqual(oldNames),"original names pointer/label/size/capacity restored exactly");Check(Read(state+32,32).SequenceEqual(updatedTypes),"Unity-updated types vector preserved byte-for-byte");
Marshal.WriteIntPtr(state,new IntPtr(0x5555));var restored=Read(state,64);manager.GetMethod("RestoreOriginalAssemblyNamesArrayPtr").Invoke(instance,null);Check(Read(state,64).SequenceEqual(restored),"second restore is idempotent and does not rewrite native state");
foreach(var name in new[]{"AwakeFromLoad","IsAssemblyCreated","IsFileCreated","ConvertSeparatorsToPlatform","ScriptingManagerDeconstructor"}){var t=a.GetType("FixPluginTypesSerialization.Patchers."+name,true);var callback=t.GetField("HookCallback",BindingFlags.NonPublic|BindingFlags.Static);Check(callback!=null&&callback.IsInitOnly,"static readonly callback root exists: "+name);}
Console.WriteLine("Synthetic owned-memory test only: no Unity, native hooks, allocator release, Wine or gameplay executed.");
}finally{field.SetValue(null,IntPtr.Zero);Marshal.FreeHGlobal(state);Marshal.FreeHGlobal(global);}}}