# 研究结论与兼容性边界

研究日期：2026-10-17（Asia/Shanghai）。本文件区分源码事实、项目文档事实、设计选择和待验证假设；网页的“最新”不是本项目已验证的版本。

## 路线选择

采用用户合法持有的 **Steam Windows 客户端文件 + Linux amd64 容器 + Wine + 按原始 DLL SHA-256 锁定的实验性兼容补丁** 作为研究路线。Docker 只包装运行环境，不把 Windows 游戏变成原生 Linux 程序。当前修复候选已在目标软路由创建真实 Steam server，返回 lobby A2S 查询，并接受一台同 build 原版 Windows 客户端通过 LAN 加入大厅；尚未验证 Steam 最终登录、开局及完整对局。最新证据见 [实际验证状态](status.md)。

上游 [albodin/RoR2Server](https://github.com/albodin/RoR2Server) 的 README 明确采用客户端文件改造，声称官方专服陈旧；这是上游的判断，并非当前官方支持承诺。官方 Steam 专服 App 1180760 是否与当前客户端兼容，必须实际下载并握手检查，不能仅凭 App 存在或元数据更新时间作结论。本项目不默认以旧专服下载结果替代当前客户端文件，也不分发游戏文件。

[Steam 官方商店](https://store.steampowered.com/app/632360/Risk_of_Rain_2/) 在研究日列出 2026-10-08 的 Hallowed Concepts 更新；[Steam 官方公告列表](https://store.steampowered.com/oldnews/?appgroupname=Risk+of+Rain+2&appids=632360&feed=steam_community_announcements&headlines=1&l=koreana) 列出 2026-10-14 Hotfix。这表明不能用旧 `1.3.9` 或 `1.4.1` 字符串作为“最新兼容”依据。用户更新后的本地 Steam manifest 已核实为 build `25921972`，纯净来源已导出，原始 `RoR2.dll` SHA-256 为 `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`。目标 Wine 日志确认 Unity `2021.3.45f2`。这些是当前测试来源，不构成对未来 Steam 更新的兼容承诺；所有参与客户端仍须使用相同 stable 分支及玩法 Mod 清单。

## 上游源码审计

以下是对[原始 Program.cs](https://github.com/albodin/RoR2Server/blob/master/RoR2Patcher/Program.cs)及仓库内初始文件的静态分析，未在真实游戏验证：

| 操作 | 实际作用与风险 | 改造原则 |
| --- | --- | --- |
| DedicatedServer 标志 | 按短 IL 模式把 Steam 服务端标志从 false 改 true；只改标志不等于完整初始化 | 唯一候选位置、调用签名、预期次数全部验证后才能输出 |
| AppID 替换 | 在大量方法里把客户端数字替换为专服数字，范围宽 | 不全程序集盲替换；先证明目标 Steam 服务端调用需要什么 |
| RunConfigsAfterLoad | 插入网络消息处理器收集与启动配置执行 | 必须证明当前版本已初始化哪些 handler，避免重复注册；顺序必须核验 |
| Lobby 构造器替换 | 删除相邻局部变量 IL，换构造器 | 需验证栈、分支引用和构造器签名；不能当作跨版本通用补丁 |
| SkipSteamClientInit | 实际只把 `steamworksFailed = true` 改为 false | 名称不代表行为；掩盖失败无法证明 Steam 初始化成功 |
| BuildId / 版本校验 | 把版本写死或把校验调用换成常量 | 移除这种做法；版本号相等不保证网络结构兼容 |

此外，上游启动脚本写出 `server.cfg`，补丁插入的却是 `exec server_startup`；配置是否被加载不能推定。以 `.bak` 是否存在决定跳过补丁，也无法识别 Steam 更新后的 DLL。启动脚本以 `tail -f` 存活并不等于游戏存活。

## 启动参数的证据边界

[Unity Player 参数文档](https://docs.unity3d.com/Manual/PlayerCommandLineArguments.html)说明 `-batchmode`、`-nographics`、`-logFile` 的引擎含义；应对照实际游戏 Unity 版本文档。无图形批处理运行 **不证明** 游戏进入专服模式。上游也是依靠程序集补丁而非一个已证实的 `-dedicated` 开关。

当前未找到足够一手证据证明最新版 Steam 客户端仅添加 `-dedicated`、`+sv_*` 或 `+exec server_startup.cfg` 即可无补丁开服。这些均只能作为待验证候选，不能在说明中称为可靠启动入口。`sv_*`、`host 1` 等由游戏自己的控制台处理，不是 Unity 的通用参数；应先从当前 DLL 审计命令注册、配置加载路径和初始化时序，再检查日志是否接受及实际端口。

## BepInEx、R2API、Thunderstore

[BepInEx 官方 Wine 指南](https://docs.bepinex.dev/articles/advanced/proton_wine.html)要求配置注入 DLL 覆盖；本路线使用 `WINEDLLOVERRIDES="winhttp=n,b"`。这是加载前提，不能替代日志中的 Chainloader 和插件成功记录。

研究日 [bbepis/BepInExPack](https://thunderstore.io/c/riskofrain2/p/bbepis/BepInExPack/) 页面显示 `5.4.2122`，其内部 `BepInExPack/` 内容需放入游戏根目录，保留 Doorstop 文件、core、patchers 和 plugins。不要把 zip 根目录不加识别地全部塞进 plugins。`bbepis/BepInExPack` 与 [RiskofThunder/RoR2BepInExPack](https://thunderstore.io/c/riskofrain2/p/RiskofThunder/RoR2BepInExPack/) 是不同包，后者是游戏 Mod 兼容修复层，不是前者的同名替代品。

[R2API 项目](https://github.com/risk-of-thunder/R2API)从 5.x 拆为模块，优先按 Mod manifest 安装所需的 `RiskofThunder` 模块及递归依赖。[R2API.Core 变更记录](https://github.com/risk-of-thunder/R2API/blob/master/R2API.Core/README.md)的 `5.3.0` 提到针对游戏 `1.4.1` 的修复；它不证明对研究日新更新的兼容性。加载成功也不保证所有 Mod 支持无渲染、无本地玩家、Steam 专服和不同 DLC 内容。

采用固定版本、固定 SHA-256、离线可重现的 Mod 集。每个包记录团队名、包名、版本、依赖、来源、hash、安装文件清单、客户端需求和已测试状态。玩法/网络/内容 Mod 默认要求客户端同版本；仅在作者明确标注且实测后才能归为 server-only。任意 Thunderstore 包不是普遍兼容承诺；增加一个包就重跑验收。

## 目标设备

[Intel N5105 官方规格](https://www.intel.com/content/www/us/en/products/sku/212328/intel-celeron-processor-n5105-4m-cache-up-to-2-90-ghz/specifications.html)：4 核 4 线程、64 位、最高 2.90 GHz、标称 10 W、官方最大内存 16 GB。设备支持 amd64 路线，但没有实测证据保证后期高怪物密度、4 人或任意大型 Mod 包的帧时间。内存扩展不能解决单线程饱和、过热或路由软中断争用。

目标主机已实测为 ImmortalWrt 25.12.1、Linux 6.12.94 x86_64、Docker 27.3.1、cgroup v2，详细证据见 [router-assessment.md](router-assessment.md)。Docker 基础镜像及项目运行镜像已在软路由构建，UID/GID 1000 的基础 smoke 确认 Wine 8.0、Python、Xvfb/xauth 和可写数据目录。真实游戏启动经历多轮失败后，修复候选已取得下文记录的部分运行进展；仍不能把 smoke、补丁回读、结构测试或容器 healthy 当作游戏兼容验收。WAN 入站、防火墙、Steam 握手、多客户端和稳定性仍未通过验收；网络、主线程和实战门槛见 [network-performance.md](network-performance.md) 与 [validation.md](validation.md)。

## 真实启动中发现的边界

baseline 三项补丁输出成功后，在目标设备进入 Unity 资源加载，但记录 `SteamAPI_Init returned false`，没有可用 A2S 查询响应。早期 server bootstrap 通过真实 `StartServer()` 初始化服务端，但调用点位于游戏目录就绪之前，实测在 `RuleBook.SetToDefaults` 抛出 `ArgumentNullException: sourceArray`。这证明不能在客户端初始化委托中直接提前构造服务端。

因此新增 deferred 实验分支：跳过客户端初始化块，保留平台设置和初始 lobby 数据，交由目录加载后的普通 host 路径创建真实服务端，并将所需网络接收路径切换到 server singleton。第一版该分支虽能序列化和通过结构测试，在 Unity Mono 中仍因 `InitializeGameRoutine.MoveNext` 的 `IL_033b: dup` 抛出 `InvalidProgramException`。

后续修复候选 SHA-256 `73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07` 已在同一设备越过这些阻塞点，进入目录加载和普通 host 路径。日志为 `steamworksServer.IsValid=True`、初始 `LoggedOn=False` 和 `hostType=Self listen=True`；本地 A2S 返回 lobby，容器 healthy。修正本项目桥接网络缺少的 fw4 规则后，一台同 build 原版 Windows 客户端已通过 LAN 进入大厅，服务端接受玩家与投票，A2S 显示 1/4 玩家；27015 实际为 udp6 socket，conntrack 已观察到双向 UDP 流量。不能将这些结果扩大为 Steam 已完成登录、完整对局或公网联机成功。日志仍有重复 playerController/ready、未注册 `MsgType.Highest + 22` 和无图形 UI 空引用等异常，进一步的平台服务、P2P、Mod 和多人行为仍需验收。证据见 `output/router-deferred-verified-diagnostic-2.txt`、`output/router-client-qa-diagnostic.txt` 与 [实际验证状态](status.md)。
