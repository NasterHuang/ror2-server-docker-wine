# 实际验证状态

更新日期：2026-10-18（Asia/Shanghai）。目标是 N5105 / ImmortalWrt / Docker 上兼容当前 Steam 客户端的独立服务器。**V7 已由普通 Compose 配置重建，并独立完成加载、host、Steam登录、单客户端LAN加入和首关启动。03:42本轮服务端与只读客户端样本均为golemplains2、runActive=true，各记录1个玩家受控实体和5个怪物实体，服务端真实认证成功1、失败0。这证明单客户端游戏链路及复制对象观察，尚不证明可视化游玩、伤害、拾取、时钟一致或同步质量。双客户端、WAN 和占用对局长时验收仍未完成。** 以下保留历史失败与当前结果；容器健康和结构测试不构成稳定多人游戏就绪。

| 层级 | 项目 | 实际结果 | 证据与边界 |
| --- | --- | --- | --- |
| 实际部分通过 | 本项目开机启动助手 | 已安装、启用并检查所有权、幂等启动、status；未实机重启 | `output/router-v7-boot-service-final.txt`、`output/router-boot-status-final.txt`；procd助手不重启其他容器，Docker有限重试仍为3次 |
| 来源已核实 | Steam build `25921972` | 用户更新后已核实、导出纯净来源 | 原始 `RoR2.dll` SHA-256：`48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`；原玩家目录未改写 |
| 静态验证 | 精确 SHA / 签名 / IL 位置与补丁回读 | 已实现且通过相应测试 | 只证明受审计的变换可生成和回读；不证明 Unity Mono 接受或游戏服务端可用 |
| 镜像已验证 | 软路由 Docker 基础镜像及项目运行镜像 | 已在真实软路由构建 | `output/router-base-build-result.json`、`output/router-final-build.log`；非其他主机替代验证 |
| 环境 smoke | 非 root UID/GID 1000、Wine 8.0、Python、Xvfb、xauth、可写 `/data` | 已通过 | `output/router-base-smoke.json`；该测试没有启动游戏，也未测试 Mod 或 Steam |
| 实际失败 | baseline 三项补丁启动 | Unity 资源加载后 Steam 初始化失败，无可用查询响应 | `SteamAPI_Init returned false`；`output/router-baseline-diagnostic*.txt` 和 `output/router-baseline-logs.txt` |
| 实际失败 | early server bootstrap / server networking | 初始化过早，游戏目录尚未就绪 | `RuleBook.SetToDefaults -> SteamworksServerManager` 抛出 `ArgumentNullException: sourceArray`；`output/router-bootstrap-diagnostic-3.txt` |
| 实际失败 | 第一版 deferred server | Unity Mono 拒绝生成的 IL | `InitializeGameRoutine.MoveNext`：`InvalidProgramException`，`IL_033b: dup`；`output/router-deferred-diagnostic.txt` |
| 实际部分通过 | deferred 修复候选 | 越过此前 Mono IL 与 RuleBook 阻塞点，进入目录加载和 host 路径 | 已部署候选 SHA-256 `73462114c898c9b326703e5434cd820e70289715e7513bd082a61d36cc114c07`；`output/router-deferred-verified-diagnostic-2.txt` |
| 实际部分通过 | Steam server 创建、host 状态与本地 A2S | `steamworksServer.IsValid=True`，`hostType=Self listen=True maxPlayers=4`，容器 healthy | 查询返回 `RoR2 N5105 experimental`、`map=lobby`、`players=0`、`maxPlayers=4`、`appId16=0`；仅证明此查询链路工作 |
| 实际部分通过 | 单客户端 LAN 大厅 | 同 build `25921972` 原版 Windows 客户端通过 `connect` 进入；服务端收到玩家和 `Accepting vote`，A2S 显示 1/4 玩家 | `output/client-qa-diagnostic.txt`、`output/router-client-qa-diagnostic.txt`；仍有重复 ready/playerController 警告，未证明开局或稳定对局 |
| 实际部分通过 | 本项目 LAN 防火墙修正 | 精确临时规则后 LAN A2S 成功；后续已改固定桥 `br-ror2` 与持久 UCI `ror2` zone，`fw4 check`、reload 和本项目网络重建已执行 | `output/router-fw-diagnostic-applied.txt`、`output/router-baseline-stable-network-rollout.log`；未重启其他容器。27015 为 udp6 socket，先前双向 conntrack 为 ASSURED；尚须主机重启后复测 |
| 实际观察 | 大厅限帧后的资源快照 | 显式 `vsync_count 0; fps_max 60;` 后，某次空大厅采样 CPU 21.95%、内存2.348GiB/4GiB，A2S healthy | `output/router-capped-baseline-diagnostic-2.txt`；早先111.61%是不同时间单点，不能据此计算优化收益或宣称降低对局延迟 |
| 历史部分通过 | v3 Mod 大厅及 Steam 后台 | 6插件Chainloader、游戏初始化与Steam登录前进，但FPTS1.0.3序列化修复仍失败 | `output/router-audio-loader-1.txt`、`output/router-audio-game-with-client-1.txt`；不能把v3称为完整兼容组合 |
| 实际失败 | v4官方FPTS1.0.4 | 使用精确PDB偏移后，仍因旧StringView ABI发生native crash | `output/router-mod-v4-native-exit.txt`；`output/candidate-v4.lock.json`为失败复现输入，不能直接当作可运行组合 |
| 历史部分通过 | V5本地FPTS源码候选 | DLL `43b4ddae…`实际加载6插件，gameLoadFinished/serverActive/steamIsValid/steamLoggedOn均true，CM connected累计1，进入Mod lobby | `output/router-v5-boot-2.txt`、`output/router-v5-current.txt`；源码commit `7b7b2a596c18f1f9bb4ae9ddedfe1eea18cecb7c`，该版本样本玩家认证成功回调为0，未完成Mod客户端加入 |
| 历史首启样本 | V6 FPTS维护补丁首次Wine大厅 | 镜像 `284f668f0912`、DLL `1d0ac76e…`实际加载6插件，约125秒loadFinished，serverActive/steamLoggedOn=true、CM connected累计1，healthy | `output/router-v6-game-ready.txt`、`output/router-v6-startup-state.txt`；该首启样本玩家认证回调为0；后续加入和受控停止结果另列，Unity原生析构、再次启动就绪和长时稳定仍待验收 |
| 实际部分通过 | V6 单客户端 LAN Mod 大厅及玩家认证 | 2026-10-17 19:34 服务端 networkUsers=1、Steam认证成功回调累计1、失败0，客户端出现添加本地玩家日志；现场 A2S 查询为1/4 | `output/router-v6-client-retry-2.txt`、`output/client-qa-v6-mod-lobby.log`；A2S现场输出未单独留档。runActive=false，仍有重复ready/playerController和无图形UI警告，未证明开局或完整对局 |
| 实际观察 | 相隔约8小时的 V6 大厅复查 | 2026-10-18 03:25 healthy、Steam在线、networkUsers=0；CM connected累计2、disconnected累计1，最后事件为connected；当前CPU22.41%、内存2.54GiB/6GiB | `output/router-resume-current.txt`；与前一晚样本相隔约7小时50分，期间出现过Steam断连与重新连接。仅大厅两端样本，不证明全程无波动，也不是占用对局soak |
| 实际部分通过 | V6 服务端开始首关 | 2026-10-18 03:28:54 通过原版 `pregame_start_run` 后，runActive=true、scene=golemplains2、networkUsers=1、Steam认证成功回调累计2、失败0 | `output/router-resume-run-result-1.txt`；该样本仅确认服务端Run及首关场景，后续客户端遥测见下一行，不构成实战或同步通过。切图窗口Unity帧间隔含1562.945ms最大值，不能当作稳态性能 |
| 实际部分通过 | V6 单客户端首关复制对象 | 03:33:03 客户端 clientActive/clientSceneReady/runActive=true、scene=golemplains2、networkUsers=1；Run计时12.55秒时bodies=9、playerControlled=1、monster=8，167.69秒时bodies=30、playerControlled=1、monster=29 | `output/client-telemetry-run-first-20261018.json`、`output/client-telemetry-run-before-maintenance-20261018.json`；只读探针源码在 `Diagnostics/ClientProbe`，程序集SHA前缀 `594b…`。证明batchmode单客户端收到复制对象，未证明可视化游玩、伤害、拾取、RTT、怪物运动质量或多人稳定 |
| 实际通过（受控容器停止） | V6停止 | `docker stop` 后 exitCode=0、OOMKilled=false | `output/router-v6-normal-stop-20261018.txt`；supervisor使用 `wineserver -k` 清理本项目Wine进程，因此不能据此宣称Unity原生析构路径通过 |
| 实际部分通过 | V7 服务端实体遥测候选就绪 | ServerTools DLL SHA前缀 `022d5abc…`，仅新增实体遥测；FPTS仍为V6的 `1d0ac76e…`。镜像 `152791965609714132ea51cae0ec5d1fa70bcf62634975e942d0d586ebaa074c` 由普通Compose重建，restart为on-failure最多3次、默认启动期限600秒。03:40样本loadFinished/serverActive/steamLoggedOn=true、CM connected累计1、healthy，空大厅实体数0 | `output/router-v7-recreate-normal.txt`、`output/router-v7-steam-ready.txt`；空大厅CPU22.35%、内存2.517GiB/6GiB，仅单次资源快照。此轮后续加入和首关结果见下一行 |
| 实际部分通过 | V7 独立复测单客户端加入及首关复制对象 | 03:42:32服务端与03:42:33客户端均为golemplains2、Run进行中、networkUsers=1；双方各记录bodies=6、playerControlled=1、monster=5，服务端认证成功1/失败0，新增服务端实体遥测已实际执行 | `output/router-v7-run-20261018.txt`、`output/client-v7-run-20261018.json`；服务端Run计时14.483秒、客户端16.9999秒，两个样本非原子且包含采样时差/预测，不能宣称时钟完全一致或同步质量通过。服务端CPU50.33%、内存2.562GiB/6GiB为单首关快照，不是性能基准 |
| 实际通过（LAN查询） | A2S完整字段与实际AppID | gameId64=632360、解析AppID=632360、appId16=0、EDF=177、gamePort=27015、players=1、map=golemplains2、version=1.5.0、VAC字段1、visibility字段1 | `output/lan-query-detailed-20261018.json`；保留16位wire值0，实际AppID已由可选GameID字段核实。查询字段不证明公网可达或VAC运行效果 |
| 实际通过 | 卡启动超时退出 | 120秒诊断期限后退出码1，停止本项目游戏进程 | `output/router-bounded-exit-check.txt`、`output/router-phase-boot-final.txt`；默认期限600秒，不是多人通过证据 |
| 实际观察 | V5 Mod空大厅资源与帧间隔 | 单次CPU22.92%、内存2.533GiB/6GiB，目标60fps，窗口Unity帧间隔P95=17.147ms | `output/router-v5-current.txt`；仅空大厅快照，不是CPU计算耗时、物理tickrate、网络RTT或后期负载基准 |
| 下载与展开已验证 | Thunderstore候选锁与本地源码overlay | v3锁在tracked profiles，v4锁和staging在output；后续需显式源码构建/overlay及来源记录 | 官方包lock不含本地源码修复；启动进展不能等同完整Mod联机兼容，见 [profiles说明](../profiles/README.md) |
| 已准备、图形验证待完成 | V7.2客户端测试包 | `output/Rains-client-test-25921972-v7.2.zip` 约26MB，SHA-256 `26a98af3d4fb8ed8f48e93472ce789a57f854149dbb07389e28fc4862a901fe4`；包含最新preflight修正及保留上游字节的 `.gitattributes`，游戏组合及本地ServerTools `022d5abc…` 不变 | 测试包准备不等于图形客户端或公网加入通过；私人连接文件不在报告中展开 |
| 实际失败 | 首次候选 Mod 加载 | BepInEx preloader 和 HookGen 已运行，但两个 preloader 插件失败，尚未证明 Chainloader/R2API 完整加载 | `pseudopulse-SeekersPatcher-1.3.7` 字段匹配 `Sequence contains no matching element`；FixPluginTypesSerialization 下载 Unity PDB 时 `TLS Support not available`；`output/router-mod-loader-diagnostic-3.txt`，修复与升级候选待实测 |
| 实际部分通过 | Steam后台登录与单玩家认证 | V6实时LoggedOn=true；首次LAN Mod客户端加入时成功回调累计1，03:28首关样本累计2、失败0、networkUsers=1 | `output/router-v6-client-retry-2.txt`、`output/router-resume-run-result-1.txt`；累计回调数不等于独立账号数，仍未验证第二个账号、完整重连流程或对局认证稳定性 |
| 未验收 | P2P、WAN/FRP与公网玩家握手 | 已有无Mod及V6 Mod单客户端LAN大厅结果，公网链路仍未验证 | 不能由LAN加入推断Steam浏览器可见、P2P、WAN直连或FRP可用 |
| 未验收 | 多人开局、换图、重连、结算、长时稳定性 | 未完成 | 至少两个真实客户端按 [validation.md](validation.md) 执行 |
| 未验收 | 延迟、怪物瞬移、后期负载与 Mod 性能 | 未完成实战比较 | 参数配置不能证明同步问题改善；需记录帧时间、RTT、丢包和路由负载 |

## 容量与运行边界

用户已授权容量确实不足时扩容。只读复核确认当前 Optane M10 可寻址容量 14,403,239,936 字节，p3 已覆盖可用 GPT 尾部，ext4 已占满其分区，保留块为零，DockerRoot 是同一容量池中的 bind mount；当前原盘没有可直接在线扩展的完整 ext4 块。没有修改分区、文件系统参数、DockerRoot 或既有服务。

当前采取 PC 保存来源与回滚、路由单份 runtime 的实验布局；容量复核时 `/opt` 仍余约 1.3 GiB，可继续有日志限额的受控诊断。该数字是快照，后续测试需重新采样。增加存储或单独迁移本项目数据的方案及原始读数见 [router-assessment.md](router-assessment.md)；不能把其他挂载的重复视图、tmpfs 或根分区剩余空间当作 Docker 已获得扩容。

## 下一验收顺序

1. 处理日志中的 `Network message MsgType.Highest + 22 is unregistered`，核查消息注册时序与实际传输；检查 `TranslucentImageSource.CreateCommandBuffer` 的无图形 UI 空引用。还记录了缺失 `server_pregame.cfg` 和 JobTempAlloc 警告，不能在未分析前宣称无异常稳定运行。
2. 普通Compose配置下V7已独立通过ready、单客户端加入和首关复制对象观察，下一步验证占用对局长时运行；V6的受控停止已通过，但Unity原生析构路径仍未验证。持续检查CM断连/认证回调、端口和A2S广告，不能只看构造缓存SteamId。约8小时后的大厅复查已有一次CM断连后重新连接，尚无连续采样证明其间玩家连接表现。完整LAN A2S已由可选GameID核实AppID=632360；不再把保留的 `appId16=0` 单独当作广告缺陷。
3. V6和V7只读客户端遥测均已确认首关及复制对象，下一步使用同build、同候选和配置核实图形客户端的移动、伤害和拾取等实际操作，再安排第二个独立Steam账号测试两人开局、换图、掉线重连与结算，对照无Mod基线。
4. 完成 WAN 直连与必要时 FRP 的对照测试、后期高负载和长时运行，才能判断是否达到稳定部署目标。

当前只读网络复核还发现容器 TCP443 经 OpenClash fake IP `198.18.0.0/16` 重定向至透明代理，连接为双向 ESTABLISHED/ASSURED；没有证据证明本项目 UDP 被 TPROXY，实际读取的 UDP 入口链没有 mark/tproxy 动作。需要以本项目源地址进行可回滚直连对照，并同步确保 DNS 返回真实地址；不能把 fake IP 直接绕过代理后当作公网目标发送。证据为 `output/router-openclash-readonly.json`。

限帧基线日志显示 `Product=632360`、`DedicatedServer=True`，启动阶段样本为 `SteamId=0`、`LoggedOn=False`、`PublicIp` 空。`Server.SteamId` 是构造时缓存，不代表当前登录就绪。最新Mod样本已收到 CM connected 且 LoggedOn=true，说明早期false不能作最终结论；没有因此改动全局OpenClash或假定必须bypass。持久fw4转发方案见 [部署说明](deployment.md)，公网玩家连接仍须实测。

V7本次后台日志中，`GetCMListForConnect` 的WebAPI首次请求约60秒后超时，随后Steam SDK原生WebSocket fallback收到 `LogOnResponse OK`；03:40状态样本也确认CM connected和LoggedOn=true。没有改动OpenClash或伪造认证，也不能把这次fallback成功推断为公网玩家连接已通过。

完整LAN A2S响应的可选GameID为632360。依据 [Valve官方SDK的CGameID布局](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/public/steam/steamclientpublic.h#L995-L1005)，AppID占GameID低24位，因此该样本的实际AppID为632360。此前 `appId16=0` 是保留的16位原始字段，不能单独用于判定广告AppID错误；本次核实也不等同于Steam浏览器可见或公网可达。

首次Mod加载的旧SeekersPatcher字段和MiscFixes重载错误，已分别用官方1.4.4/1.6.1升级越过。其后的初始化长期等待已由只读协程状态定位为 `LoadGameContent` 状态3：内容协程栈为空，等待真实Wwise bank callbacks。精确SHA白名单适配撤销兼容包的batchmode提前失败hooks后，真实Loaded bank日志出现，初始化、host和Steam登录均前进；没有伪造pendingLoads或成功回调。之后官方FPTS1.0.4的精确符号偏移仍未解决旧StringView ABI导致的native crash；固定上游master源码的V5 DLL已越过并完成大厅启动。V6维护补丁增强native向量恢复和delegate生命周期，已通过首次Wine大厅启动（约125秒）、单客户端LAN Mod大厅加入及首关复制对象观察。V6受控容器停止exitCode=0且未OOM；因清理使用 `wineserver -k`，不能作为Unity原生析构通过证据。V7更换ServerTools加入服务端实体遥测后重新部署，已独立完成加载、host、Steam登录、客户端加入及首关，两端非原子样本均记录1个玩家受控实体和5个怪物实体；这仍不构成实际操作或同步质量验收。

当前health同时启用MODS和ServerTools时，还要求30秒内的game.json及真实loadFinished/serverActive；只有A2S或boot.json不通过。此前79项Python测试已在真实目标Linux容器通过（`output/router-v6-linux-tests.txt`）；新增测试后，本机Windows运行86项、因平台条件跳过3项，目标Linux已完成86项全部通过（`output/router-v7-linux-tests.txt`）。这些测试不代表Wine/native callbacks或游戏验收。电脑端的ActiveUser=0/SteamAPI_Init失败阻塞已越过：ActiveUser恢复且原生probe成功。首次QA在服务端就绪前连接超时（`output/client-qa-v6-early-timeout.log`），不算成功入服；服务端ready后重试，2026-10-17 19:34 获得networkUsers=1和一次真实Steam玩家认证成功回调的大厅结果。2026-10-18 03:25复查仍处大厅、没有玩家，不能把该时间跨度记为多人对局soak通过；03:28原版开局命令后服务端进入golemplains2，03:33起的客户端只读遥测随后确认同场景、Run计时及玩家/怪物复制对象。该探针不操作游戏状态；无图形客户端日志仍有UI空引用和重复ready警告，图形游玩、实战同步、换图和结算均待验收。

诊断原件位于被 git 忽略的 `output/`。报告不发布游戏程序集、连接文件、凭据或远程地址；源码中保留的是补丁逻辑、审计清单和可复现工具。

2026-10-18 03:43自动测试客户端已停止；服务端新鲜样本为Steam在线、healthy、networkUsers=0、runActive=false、scene=lobby，保留空大厅供双人测试。之后增加的开机助手4项回归检查已在目标Linux实际执行，最新完整90项全部通过（`output/router-20261018-final-90-tests.txt`）；早先86项结果保留为历史。宿主整机重启、掉电恢复与实际双人公网游戏仍待验收。

源码实现检查点为分支 `codex/steam-25921972-server` 的提交 `b83e99a`，后续文档与开机助手另有本地提交，尚未push。提交使用单次指定的 `Codex <codex@localhost>` 身份，未修改全局Git身份配置。
