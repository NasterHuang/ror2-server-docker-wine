# 精确构建性能与 headless Mod 审查

2026-10-17。只读检查实际 Steam build `25921972`，没有修改游戏、runtime 或当前候选锁。`RoR2.dll` SHA256：`48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`；`UnityPlayer.dll` 文件版本为 Unity `2021.3.45f2 (88f88f591b2e)`。使用 Mono.Cecil 读取 IL，初步全量相关方法导出到本地 `output/performance-il-audit.json`（不提交游戏代码）。

## 可证实的控制项

| 控制项 | 实际 DLL 证据 | 建议 |
| --- | --- | --- |
| `fps_max` | `RoR2.SettingsConVars/FpsMaxConVar::.cctor` offset 6 默认字符串 `60`；`SetString` offset 11 调用 `Application.set_targetFrameRate`；帮助明确 `-1` 不限帧 | 保持有限上限 `60`；没有证据支持进一步调高。不能把默认值当成实际测得帧率 |
| `vsync_count` | `VSyncCountConVar::.cctor` 默认参数 `null`，没有强制数值；`SetString` offset 11 调用 `QualitySettings.set_vSyncCount` | headless 候选配置可显式设 `0`，使软件帧率上限不被 VSync 覆盖；需实测生效和 CPU 变化 |
| `timestep` | `RoR2.EngineConVars/TimeStepConVar::.cctor` 默认 `null`；setter 直接调用 `Time.set_fixedDeltaTime` | 不改。DLL 本身不能证明 Unity 项目配置中的初始物理步长数值 |
| `sv_time_transmit_interval` | `NetworkManagerSystem::.cctor` offset 109 为 `0.01666667`；帮助说明是服务端向客户端发送**时间更新**的间隔 | 不等同统一网络 tickrate，不改 |
| 角色位置快照 | `CharacterNetworkTransform::.ctor` offset 19 为 `0.1` 秒，插值因子 offset 41 为 `2` | 是构造默认，不排除 prefab 覆写；不据此修改全部怪物发送率 |
| 视角发送 | `NetworkedViewAngles::.ctor` 默认 `sendRate=0.05`，其 `GetNetworkSendInterval` 直接返回该字段 | 与角色位置发送不是同一周期，不改 |
| 投射物位置字段 | `ProjectileNetworkTransform::.ctor` 初始 `positionTransmitInterval=0.03333334`，插值因子 `1` | 类内部仍调用 UNet `GetNetworkSendInterval`；不能直接把字段当成所有投射物有效发送频率 |

现有 `RoR2.Console::InitConVars` offset 98 会对默认值调用 `AttemptSetString`，所以 `fps_max=60` 不是单纯说明文字。但是未通过运行时读取证明 Wine/headless 中的最终 `targetFrameRate`、VSync 和实际 Update FPS，也没有验证加载阶段 CPU 占用发生时是否已执行该初始化。

Unity 2021.3 官方说明：桌面 `vSyncCount!=0` 时 `targetFrameRate` 可能被忽略；两项应配套审查。[Unity 2021.3 targetFrameRate](https://docs.unity3d.com/2021.3/Documentation/ScriptReference/Application-targetFrameRate.html)。`-batchmode -nographics` 是桌面 headless，不能获得重新构建为 Dedicated Server 目标时的全部 CPU/内存优化。[Unity headless 文档](https://docs.unity3d.com/2021.3/Documentation/Manual/desktop-headless-mode.html)。

当前“加载中占用 1–2 核”不是运行稳定后的空服 CPU 基准。先达到服务器可查询、场景稳定后，观察至少数分钟的 CPU、日志增长和帧间隔，再判断是否存在空转。仅显式 `vsync_count 0; fps_max 60;` 有明确 API 路径支持作为候选；没有实测就不能报告节省了多少 CPU。`fps_max 30` 可以作为独立空服实验，但它降低主循环频率，可能影响更新节奏，未验收前不作为默认；不改 `timestep`、物理自动模拟或同步间隔来换低 CPU。

## 8 包 candidate 的 GUI 风险

检查实际缓存中 `RiskofThunder-BepInEx_GUI-3.0.1` 的 `BepInEx.GUI.Loader.dll`：

- `Config::Init` 将 `BepInEx/config/BepInEx.GUI.cfg` 的 `[Settings] Enable BepInEx GUI` 默认绑定为 **true**（offset 47）。
- `Patcher::InitializeInternal` 先检查常规 BepInEx console 是否启用，然后检查 GUI 配置并可能调用 `FindAndLaunchGUI`；该方法没有 headless / batchmode 检查。
- 实际 BepInEx core 的 `ConsoleManager::.cctor` 将 `[Logging.Console] Enabled` 默认绑定为 **false**。
- GUI 包包含 `bepinex_gui.exe`，能启动独立进程并建立日志 socket。默认配置可能在 Xvfb/Wine 下多启动不需要的 GUI；目前没有运行验证它实际启动或消耗了多少资源。

最稳妥的第一步是保留完整依赖，在部署持久配置中明确关闭 GUI，而不是删除 manifest 要求的包：

```ini
# BepInEx/config/BepInEx.GUI.cfg
[Settings]
Enable BepInEx GUI = false
```

常规 console 保持关闭并保留可审计的磁盘日志；稳定期可以缩减 Debug 级别，但保留错误及关键启动证据。不要在故障定位阶段关掉所有 Unity/BepInEx 日志。

在线查看 `bbepis-BepInExPack-5.4.2120` API 后确认它也依赖相同的 GUI、序列化修复、RoR2BepInExPack、SeekersPatcher、MiscFixes 五包；简单降到 R2API_Core manifest 写的旧 loader 版本**不能减少依赖**。当前 8 包已经是三个显式根和其完整传递依赖，未发现有证据支持且保持完整依赖的更小组合。[5.4.2120 API](https://thunderstore.io/api/experimental/package/bbepis/BepInExPack/5.4.2120/)。

当前显式版本覆写仍为 `BepInExPack 5.4.2122` 覆盖各包的旧 loader 要求，`RoR2BepInExPack 1.46.0` 覆盖 loader manifest 的 `1.9.0`。GUI 的配置关闭不改变包依赖，因此无需伪造或删改锁。SeekersPatcher / MiscFixes 会额外修改游戏行为，它们对该最新构建和独立服务器补丁的组合仍需实测；不能因它们是依赖就认定兼容。
