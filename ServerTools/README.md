# Rains Server Tools（可选，实验）

这是本项目自己的 BepInEx 5 插件，默认不运行，依赖候选包已包含的 R2API_Core 5.3.0 读取网络兼容元数据，不对网络、认证、游戏规则或怪物同步作补丁。只有同时满足环境变量 `RAINS_SERVER_TOOLS=1` 和 Unity `Application.isBatchMode` 才启用。等待 `RoR2Application.loadFinished` 后才读 Steam singleton 和游戏状态。该插件本身不证明服务端已通过多人兼容验收。

同一程序集另含可选插件 `Rains Client Wwise Compatibility`，只在 `RAINS_RESTORE_CLIENT_WWISE=1` 且 batchmode 时启用。RoR2BepInExPack 1.46.0 的 [SaferWWise](https://github.com/risk-of-thunder/RoR2BepInExPack/blob/5a95f1a1b2befc1c11e87321e217cb5a538c57a2/src/ModCompatibility/SaferWWise.cs) 将 batchmode 视为没有原生 Wwise，并使所有返回 AKRESULT 的方法直接失败。本项目运行的是保留真实 `AkSoundEngine.dll` 的客户端；`LoadGameContent` 又会等待真实 soundbank callbacks，实际停在状态3。适配插件仅对代码中固定 SHA 的当前游戏、原生音频 DLL 和兼容包调用上游自身 `SaferWWise.Disable()`，撤销这组提前失败 hooks、恢复原始原生调用；不设置成功结果、不改 pendingLoads、doneLoading 或回调，不跳过游戏加载条件。未匹配文件时拒绝执行，更新游戏或包后必须重新审计。不要热卸载/重启该兼容包组件；维护时完整重启游戏。普通图形客户端无需启用此开关。当前变更仍须实际音频初始化、回调、host 和联机测试。

插件声明 `R2API.Utils.NetworkCompatibility(CompatibilityLevel.NoNeedForSync, VersionStrictness.DifferentModVersionsAreOk)`，并使用 BepInEx 对 `com.bepis.r2api` 的硬依赖。这只说明本观测插件无需客户端同步安装，不跳过游戏 build、认证或其他 gameplay Mod 的一致性检查，没有使用通用 IgnoreNetChecks。命名空间、枚举值及 Core GUID 已从当前候选包实际程序集元数据核查。

## 构建

在项目根目录执行：

```powershell
& "$env:TEMP/rains-dotnet-sdk/dotnet.exe" build ServerTools/ServerTools.csproj -c Release
```

默认只引用本机 `output/source-25921972/Risk of Rain 2_Data/Managed` 中的原版 DLL、`output/mods-candidate/BepInEx/core/BepInEx.dll` 和候选 staging 的 `RiskofThunder-R2API_Core/R2API.Core/R2API.Core.dll`，均为 `Private=false`。可用 MSBuild `-p:GameManaged=... -p:BepInExCore=... -p:R2ApiCore=...` 指定路径。构建输出只部署 `ServerTools/bin/Release/netstandard2.1/Rains.ServerTools.dll` 到服务端 Mod staging 的 `BepInEx/plugins/Rains.ServerTools/`；游戏 DLL、Unity DLL、BepInEx 和 R2API 副本不得随插件分发。

最初尝试 `netstandard2.0` 时，当前原版 `RoR2.dll` 和 `com.unity.multiplayer-hlapi.Runtime.dll` 都要求 `netstandard 2.1.0.0`，编译器拒绝并给出 CS1705。因此插件实际目标为 `netstandard2.1`，没有隐藏或抑制版本冲突。构建针对 Steam build 25921972、原版 RoR2 SHA256 `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`；更新游戏后必须重新编译、检查 API 并实测。

修改 Mod staging 后应重新生成 runtime 和 release 的 `modsInventory`，不要直接绕过部署完整性校验。Compose 环境变量必须显式传入容器，插件不自行读取 `.env`。删除插件或移除开关可停用；旧 status 文件仍可能存在，读者必须检查 `sampleUtc` 是否新鲜。

## 观测

当前源码还包含每五秒一次的 Run 与实体观测：读取 `Run.stageClearCount`、`GetRunStopwatch()` 和 `CharacterBody.readOnlyInstancesList`。实体采样有独立时间戳与缓存，本地 `status` 请求不会提高枚举频率。玩家控制身体与 Player 阵营分别计数，后者可能包含无人机；这些是现存组件数量，没有存活过滤，不能当作活怪数或客户端复制成功的证明。部署该新版 DLL 时须更新 release 清单；旧运行候选不会自动具有新增字段。

每 5 秒在 Linux `/data/status/game.json` 写一次完整样本，临时文件与目标同目录，通过 `File.Replace`（已有目标）或 `File.Move`（首次）切换。Wine 下显式访问 `Z:\data`，映射到容器 `/data`，避免写入 Wine C 盘。目录须对运行 UID 1000 可写。

另有 `/data/status/boot.json`：Awake 写首条样本，主线程 Update 每5秒更新场景、帧计数、加载完成标志及初始化线程/队列状态。当前 build 的 `SystemInitializerAttribute` 静态构造已审查，仅初始化布尔、列表及22ms预算；诊断只读取字段，不执行初始化器、不枚举队列、不写游戏状态。字段可能在采样之间变化，不能把它们当原子快照。主线程卡在同步调用中时 Update 无法执行，boot 时间停止本身是诊断信号，不能据此独自判定死锁。此文件不满足游戏就绪检查。

针对该精确构建，还用 Harmony 为 `InitializeGameRoutine` 的 `MoveNext` 追加前后观察器，将进入及 yield 后的数字状态写入 boot.json。观察器不改变返回值、迭代器字段、异常或枚举器调度，只在捕获的 Unity 主线程采样；自己的 I/O 错误不会传播到游戏。类型缺失时记录诊断错误而不猜测其他方法。该观测会增加启动期文件 I/O，性能测量应注明启用状态。游戏初始化函数内部原有 `PrintSW` 是空方法，不能把日志里没有阶段输出解释成没有运行。

开关名和值均为 ASCII；使用 `Environment.GetEnvironmentVariable` 从游戏进程环境直接读取精确值 `1`，不存在插件自己的字符编码或布尔转换。仍须在目标 Wine 进程中通过 enabled 日志确认环境继承，不可只检查宿主 shell。`Z:` 必须实际映射 Unix `/`，且 `/data/status` 的临时文件与目标处于同一文件系统。目标 Mono/Wine 必须支持 `File.Replace`；插件不会退回“删除旧文件再改名”而破坏原子性。实际验收应观察至少两个递增的 `sampleUtc`，从而覆盖首次 Move 和后续 Replace，单个新文件不足以确认替换兼容。

字段包括实际 Facepunch server singleton 的存在、`IsValid`、`LoggedOn`、SteamId 是否非零；`NetworkServer.active`；`NetworkUser` 数量；`Run` 是否存在、当前 scene、目标 FPS，以及最近窗口 Unity `unscaledDeltaTime` 的样本数、均值、P95 和最大帧间隔（毫秒）。每窗口最多 4096 样本，写成功后清空。所有游戏 API 访问在 Unity 主线程执行。

`steamIdCachedNonzero` 明确是 SDK 构造时缓存的值：当前 SDK 只在 constructor 赋值 `Server.SteamId`，它不是实时 readiness、CM 已连接或认证证据。实时 `LoggedOn` 和后续回调须分别解读，插件没有把它们合成为未经验证的 ready 标志。

额外通过公开 `BaseSteamworks.OnAnyCallback` 追加监听 CM 连接生命周期，Server 引用变化及销毁时移除自身委托。严格只允许当前 Facepunch SDK 程序集的三个类型：`SteamServersConnected_t`、`SteamServerConnectFailure_t`、`SteamServersDisconnected_t`，分别累加 `steamCmConnectedCallbacks`、`steamCmConnectFailureCallbacks`、`steamCmDisconnectedCallbacks`。这些 callback struct 和字段在 SDK 内是 internal，因此只对精确白名单类型读取名为 `Result` 的 enum 数字和 `StillRetrying` 的 bool，绝不枚举其他字段、调用对象 ToString 或记录其他 callback 内容。`steamCmLastEvent`、`steamCmLastEventUtc`、`steamCmLastResultCode`、`steamCmLastStillRetrying` 是最近一个允许事件的快照；不适用或未观察到时为 null。解析异常只增加 `steamCmDecodeErrors`，不抛给游戏。计数是线程安全累计值，快照以不可变对象发布；启动前事件不回溯，单次失败或 StillRetrying 不等于最终失败。不得把 CM 回调累计数当作当前连接状态或玩家认证数。

帧间隔包含等待、调度等因素，并非 CPU 函数耗时、物理 tickrate 或客户端 RTT。`LoggedOn=true` 说明该 SDK 当时的登录状态，不等于每名玩家的后台票据均已认证。没有收集玩家姓名、SteamId、IP、密码或票据。I/O 错误只记录异常类型，重复错误限量输出；失败时保留旧完整样本，调用方必须按时间判断失效。

`steamAuthValidationOkCallbacks` 与 `steamAuthValidationFailureCallbacks` 记录插件本次进程生命周期中实际观察到的 Facepunch `ServerAuth.OnAuthChange` 回调次数，分别为当前 SDK 的 `Status.OK=0` 和状态 1..9。后者包含未连接 Steam、许可失效、封禁、重复登录、检查超时、票据撤销及无效票据等；它不等同于初次加入失败人数，可能包含后续撤销和重新验证。所有计数使用 `Interlocked` 更新/读取，没有保存或日志输出回调的两个 SteamId 参数。零次不证明验证成功或失败，订阅前的回调不回溯；累计成功回调也不是当前已认证玩家数。读取字段是独立快照，可能跨一次并发回调。

只在游戏加载完成且实际 `Auth` 存在后用 `+=` 追加观察回调，保留游戏现有验证和踢人回调；Auth 引用变化与插件销毁时用 `-=` 撤除自身回调。不订阅只表示收到客户端认证数据的 `ServerAuthManager.onAuthDataReceivedFromClient`，不修改认证结果或游戏权限。

## 本地管理文件

仅提供本地文件接口，不开 TCP、HTTP 或 RCON。管理员通过 SSH 在容器绑定的 `/data/admin` 写临时文件后 `mv` 为 `request.txt`。不要让不受信任用户写此目录。插件每 0.5 秒将请求原子改名为唯一 `processing-*.txt` 后读取，并在 `finally` 删除；进程在领取后崩溃时不会自动重放，残留 processing 文件供人工检查。单条请求最多 128 字节，只识别去除首尾空白后完全相等的命令：

| 请求 | 行为 |
| --- | --- |
| `status` | 立即写样本 |
| `steam-info` | 固定调用原版 `steam_server_print_info`，结果在本地游戏日志；可能包含服务器 SteamId，不对外上传 |
| `start-run` | 只在服务器 active、已有 NetworkUser、存在 PreGameController 且无 Run 时提交原版 `pregame_start_run` |

未知输入（包括参数、分号、多条命令）被拒绝，原始内容不写日志或状态文件。`lastAction` / `lastActionResult` 提供最近已领取请求的结果；没有请求 ID 或队列，管理员必须一次提交一条并等待确认。

原版 IL 检查确认 `CCPregameStartRun` 对应 `pregame_start_run`，调用带服务器检查的私有 `StartRun()`，并保留其 entitlement 检查和 `NetworkSession.BeginRun` 路径。插件通过固定 Console 调用该命令，不反射调用 private 方法、不伪造票据、不强制跳过游戏权限。`submitted` 仅表示已提交；必须观察后续 `runActive`、scene 和实际客户端来确认开局成功。

```sh
mkdir -p /opt/ror2/data/admin
printf '%s\n' status > /opt/ror2/data/admin/request.tmp
mv /opt/ror2/data/admin/request.tmp /opt/ror2/data/admin/request.txt
```

## 验证边界

已完成对当前本地原版引用的 Release 编译（零警告、零错误）及输出清单检查。Wine 下原子替换行为、BepInEx 实际加载、后台 Steam 状态、请求执行和客户端开局须在真实容器中继续验证，不能由编译成功推断。
