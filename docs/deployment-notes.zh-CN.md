# 历史部署工程记录

本文保留整理前的部署观察和实现细节，包含当时的设备状态及配置。安装步骤请优先阅读 [当前中文指南](deployment.md) 或 [English guide](deployment.en.md)。以下内容是历史记录，不是新一轮实机验证。

# Docker 部署与维护

本项目目前是实验候选，不能把镜像构建、A2S 响应或 IL 合成测试视为最新游戏多人兼容验收。最新本地 Steam build 为 `25921972`；见实际测试记录及 `validation.md`。

## 两种存储方式

通用方式：`game/` 为原版只读来源，`mods/` 为完整、离线锁定的 Mod staging，`config/patch-manifest.json` 为针对该 DLL 的人工审查清单。`data/` 可写。每次启动在临时目录组装、验证并补丁，然后保留上一 runtime 后切换，失败不修改原版。建议至少 20 GiB 可用存储。

此前检查路由器 `/opt` 约有 7.1 GiB 可用，游戏单份约 3.84 GiB；这只是当时的测量值。用户已确认软路由使用 16 GB 傲腾 M10，并授权在需要时将余量扩入 Docker。扩容前仍须现场确认分区、文件系统、挂载点和 Docker data-root，保留现有容器数据；不能仅按磁盘标称容量假设 Docker 可用空间。`compose.router.yml` 采用电脑预制、路由器单份运行：原版、归档及回滚版本保存在电脑；传输完整后才启动。它牺牲路由器本地即时回滚能力。部署前计算镜像实际占用、Wine prefix 和 Mod 体积，保留至少 1 GiB 可用磁盘。

## 电脑导出原版

先在 Steam 完成更新并验证文件，然后用 Python 3.11+：

```powershell
python tools/snapshot.py --game 'G:\SteamLibrary\steamapps\common\Risk of Rain 2' --target output/source-25921972 --steam-manifest 'G:\SteamLibrary\steamapps\appmanifest_632360.acf'
```

导出白名单只包含游戏、Unity 和 Mono 文件，不导入根目录旧 loader、Mods 或 r2modman。工具检查 Steam 状态和复制前后哈希；Steam 文件本身是否原版仍以 Steam 验证为准。不会修改玩家客户端。

## 补丁审查与预制

```sh
dotnet run --project RoR2Patcher -- --inspect --input '/path/to/Managed/RoR2.dll' --report output/audit.json
```

审查该输入 SHA256 对应的全部启动路径、静态/实例调用、Steam server 初始化及版本认证。manifest 中的偏移不是跨版本接口。缺少任一需要的初始化转换，就不能认为实验已具备独立开服能力。清单格式见 `RoR2Patcher/README.md`（若无此文件则参考其测试 fixtures）。不得用关闭认证、改写 build ID 或把失败标志设为成功替代实现。

预制时设置 `ACK_EXPERIMENTAL=1`、`EXPECTED_GAME_SHA256`、`PATCH_MANIFEST` 和服务端配置。可直接调用 `tools/runtime.py` 的 `prepare()` 函数在电脑构建；Linux 使用：

```sh
python3 tools/runtime.py prepare --source /srv/ror2/game --data /srv/ror2/data --mods /srv/ror2/mods --patcher /path/to/RoR2Patcher
```

默认不启用 Mod。`MODS_ENABLED=1` 时必须使用 `mods.py` 完整安装的 Windows Mono loader + 依赖 staging，不能仅复制 plugins。只固定 R2API_Core 不等于所有功能模块齐全。不要在运行中自动下载和更新。

原版 source、启用的 mods staging、Steamworks DLL 输入目录必须与可写 data 目录互不包含，工具会在复制和恢复前拒绝重叠路径。Linux 命令行持有 data 中的独占运行锁直至游戏退出；直接调用 Python `prepare()` 的维护脚本应自行串行化，且不能与正在运行的容器共享 data。

固定候选中 BepInEx_GUI 的 GUI 默认启用，未检测 batch/headless；服务端第一次加载前，应将 `profiles/server-config/BepInEx.GUI.cfg` 放到该 runtime 的 `BepInEx/config/`（通用 Linux 方式则放到持久的 `data/bepinex-config/`）。保留完整包依赖，只关闭服务端界面。普通玩家客户端不需要这项覆盖。

## 路由器准备与启动

普通部署：复制 `.env.example` 为 `.env`，填写配置和确切游戏 SHA；创建 `game/ config/ mods/ data/`，使 data 对所用 UID/GID 可写。默认 UID/GID 1000。不要给容器 privileged 或 Docker socket。

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f --tail=200
```

空间受限部署：先在电脑准备完整 runtime，再在停止服务的状态上传到 `/opt/ror2/data/runtime/`，将目录所有者设为 UID/GID 1000，并用：

```sh
docker compose -f docker-compose.yml -f compose.router.yml config --quiet
docker compose -f docker-compose.yml -f compose.router.yml up -d
```

`launch` 启动前复核原版清单、已补丁 DLL、清单及 Mod 文件哈希，再按当前 `.env` 写配置。首次 Wine prefix 初始化可能较慢。停止时只终止本容器专属 prefix 的进程。未响应 A2S 会显示 unhealthy；Docker 不会只因 unhealthy 自动重启。进程异常退出采用最多三次重启，避免配置错误无限重启挤占软路由。维护完成并充分实测后，可自行改为 `unless-stopped` 以满足重启自恢复要求。

`STARTUP_TIMEOUT_SECONDS` 默认600（允许30–3600），游戏进程启动后若始终未通过启动检查，将终止本项目专属 Wine prefix 并以失败退出，避免初始化卡住后长期占用一核。默认检查真实 A2S；同时启用 `MODS_ENABLED=1` 和 `RAINS_SERVER_TOOLS=1` 时，还必须有30秒内的 `game.json`，其中加载完成和 host active 均为 true。缺失、过期、时间戳不合法或只有 boot.json 均不通过。Steam LoggedOn 另列观测，不用缓存 SteamId 作为就绪条件；这些检查仍不能代替玩家联机验收。首次通过后不因这一启动时限强行中断对局；后续 unhealthy 仍需诊断，不承诺自动恢复当前 run。

启动校验允许游戏重写三个精确生成路径：`Mods/enabled_mods.txt`、`Risk of Rain 2_Data/StreamingAssets/ConVarNames.txt`、`config/config.vdf`；另允许游戏根目录 `logs/` 下一层的 `*.txt` 日志，不递归放行子目录或DLL。Steamworks 的三项必需 DLL 与可选 `steamwebrtc64.dll` 单独记录在 `supportInventory` 并逐项校验。此校验检测部署文件漂移，不证明 SDK 来源或游戏兼容性。

内存先设 `MEMORY_LIMIT=4g`；内存上限不是最低预留量，OOM 限制也不能避免 CPU 或网络争用。当前已有服务占约一核，必须实际测量高波次单核饱和和路由延迟。不要盲目提高 tickrate、线程数或 socket buffer。

生成配置在 `host` 前显式执行 `vsync_count 0; fps_max 60;`。不能仅凭 `fps_max` 的默认常量为60，就推断 Unity 实际限帧已生效；限帧后的某次空大厅 CPU 采样为21.95%，但尚无可对照的重复性能基准，不能把早先111.61%的单点差值当作优化收益。`timestep` 会修改物理 fixedDeltaTime，不作未经验证的变更。`steam_p2p_use_steam_server 1` 用于选择真实专服网络接口，不是提高 tickrate。`MIN_FREE_MB` 默认1024，低于共享磁盘余量时只停止本项目游戏进程。`tools/observe.py` 可采集 cgroup CPU、内存/OOM、压力和空闲空间 JSONL；这些指标不直接给出游戏帧耗时或 RTT。

## 网络与连接

游戏、query、Steam UDP 配置端口固定且互不相同，默认 `27015/27016/27017`；实际日志还可能出现 Steam SDK 动态 UDP socket，不能把三个发布端口当作完整监听清单。Compose 使用固定设备名 `br-ror2`（由 `ROR2_BRIDGE_NAME` 覆盖）并映射三个 UDP 端口。先从 LAN 测试，再测试公网。Steam/NAT、TCP 扫描或 A2S 成功都不能代替游戏连接。

本设备曾因 fw4 的 `docker` zone 只识别 `docker0`，而项目自动命名的 Compose bridge 未获许可，导致 LAN UDP 被 reject。现提供 [本项目防火墙工具](../tools/immortalwrt-firewall.sh)，仅管理带 `ror2_` 名称的五个 UCI section：独立 `ror2` zone、LAN/WAN 到三个 UDP 端口、本项目到WAN的TCP/UDP出站、到路由DNS53。zone 的 input/forward 默认 REJECT，output ACCEPT；不把所有 Docker 桥加入 LAN，不改变 Docker daemon 或其他 zone。

先创建本项目 Docker 网络，在路由器执行（端口/桥自定义时传入相同环境变量）：

```sh
sh tools/immortalwrt-firewall.sh status
sh tools/immortalwrt-firewall.sh apply
# 只删除本工具管理的五个section并重载，不恢复整份旧防火墙：
sh tools/immortalwrt-firewall.sh remove
```

该工具在 `/opt/ror2/deployment/` 保存首次 `firewall-before.uci` 和所有权标记，遇到既有未提交防火墙改动或无标记的同名 section 会拒绝覆盖；修改后先 `fw4 check`，成功才 commit/reload。check 失败会撤销本工具暂存 section；commit 后若 reload 失败则报错，**不会自动恢复整份备份**，需检查后只恢复本项目变更。apply 会允许WAN三端口，应核对实际需要；Docker既有 `ct status dnat accept` 也可能放行发布端口，zone默认REJECT本身不是严格的发布端口白名单。

目标软路由已执行固定桥网络重建、apply、check和reload，其他已有容器保持运行；日志为 `output/router-baseline-stable-network-rollout.log`。尚未验证宿主整机重启及OpenClash再次重载后的完整行为。此工具不绕过OpenClash、不更改DNS响应模式，也不提供Steam登录就绪检测；公网与Steam最终登录仍须独立验证。启动阶段的 `LoggedOn=False` 样本不能判定最终登录失败；`Server.SteamId` 是构造时缓存，也不能当作登录ready指标。

玩家从 Steam 正常启动官方原版游戏，关闭 crossplay，保持与服务器兼容的 Steam build；无需客户端 Mod、复制副本或自定义启动器。游戏控制台（`Ctrl + Alt + 反引号键`）的 LAN 连接方法：

```text
cl_password "SERVER_PASSWORD";
connect "LAN_HOST:27015";
```

当前公网入口已使用 FRP，控制台改为：

```text
cl_password "SERVER_PASSWORD";
connect "PUBLIC_HOST:28015";
```

以上均为占位符，私人连接信息另存 `output/原版客户端连接说明.txt` 和 `output/FRP公网连接说明.txt`。云端 UDP `28015/28016/28017` 分别转发到软路由 `27015/27016/27017`；frpc 的本地目标使用已验证可达的宿主 LAN IP，而非 `127.0.0.1`。云端 `27015` 为另一游戏使用，不可占用。公网 A2S 已经 FRP 连续3次成功，但广告 `gamePort` 仍是 `27015`，所以本轮不依赖 Steam 浏览器自动连接，须显式 `connect PUBLIC_HOST:28015`。

2026-10-18 13:32，未修改的原版客户端通过该 FRP 入口成功进入大厅并认证；13:32:40 服务端启动首关 `lakes`，新鲜 `game.json` 显示 `runActive=true`、1名玩家、Steam 真实认证成功1次/失败0次、玩家受控实体1个及怪物6个。诊断副本原版 `RoR2.dll` 哈希匹配，没有 BepInEx、winhttp DLL、Mod 或探针；原 Steam 安装目录未改。本次为无图形诊断，不能认定图形客户端正常游玩或客户端全部实体同步已通过。实际移动、伤害、拾取、多人、换图、复活及长时稳定性仍待实测。

软路由原生 `frpc 0.71.0` 由 `/etc/init.d/rains-frpc` 通过 procd 管理，经 TLS TCP `7000` 复用云上现有 `frps 0.71.0`，部署时没有重启现有 frps。可用该服务的 `status/start/stop/restart` 管理本项目客户端；frpc 不依赖电脑保持开机。已实测单独重启 frpc，约4秒后3个代理重新注册，公网 A2S 再次连续3次成功；游戏和云 frps 未重启，云 frps systemd `ActiveEnter` 仍为10月1日、`NRestarts=0`。活动对局中断线恢复仍待验证。维护时只操作本项目 frpc 服务，勿重启共享 frps 或改动其他游戏的端口。具体路径和性能验收见 [网络说明](network-performance.md)。

FRP 的公开配置模板为 `profiles/frpc.example.toml`，版本与计算所得 SHA 固定在 `profiles/frpc-0.71.0.lock.json`；该摘要用于复现和传输校验，本次未独立核验作者发布的摘要或签名。重新部署时从锁中的官方 HTTPS 归档提取 `frpc`，复核归档和二进制两个 SHA，使用私下保管的既有 frps token，替换模板地址与 `ROUTER_LAN_IP`，保存到 `/opt/ror2/deployment/frp/frpc.toml`。不要覆盖或重启共享 frps。该目录应为 root 所有、权限700，配置600、二进制755；认证配置不得提交到Git。

将 `tools/immortalwrt-frpc.init` 安装到已核对属于本项目的 `/etc/init.d/rains-frpc` 后，先 `ash -n /etc/init.d/rains-frpc` 及 `/opt/ror2/deployment/frp/frpc verify -c /opt/ror2/deployment/frp/frpc.toml`，再执行 `enable` 和 `start`。新部署须从外网复测查询及真实游戏连接，不能只凭配置校验通过认定可用。停用本项目公网入口可执行该服务的 `stop`、`disable`；这不停止游戏或其他 frps 客户端。

## 已批准的服务端 Mod

经用户批准，服务端已上传 `TooManyFriends 1.2.5` 与 `PillarRevive 1.1.2`。当前为最多6人、无诅咒、四项 `Monster Credits=0`；晚间追加要求 `Auto ping pillars=true`、`On Teleporter Completion Revive=true`。自动标记必须同时部署 [独服兼容组件](../Compatibility/PillarReviveHeadless/README.md)，并确认 hook 安装成功；官方1.1.2裸启用会访问不存在的本地玩家。当前完整配置为 `profiles/pillarrevive-headless.cfg`，重建命令见 [批准记录](mods-approval-20261018.md)。玩家仍使用原版 Steam 客户端；若出现 Mod/version mismatch，应修复服务端兼容性，不要求玩家安装补丁或跳过版本检查。

上传、重启和配置值不能证明功能已通过。原版单客户端经 FRP 入大厅、认证及服务端启动首关已通过；超过4人实际加入、角色操作与换图、死亡后的实际复活及其同步仍待实测。维护时保留批准版本和配置，单独记录这些验收结果。

## ImmortalWrt 开机恢复

Docker 的本项目策略为 `on-failure:3`，它与宿主开机启动分别管理。目标路由器另已安装并启用 `/etc/init.d/rains-ror2`，源文件为 `tools/immortalwrt-ror2.init`，调用 `/opt/ror2/deployment/immortalwrt-boot-start.sh`。脚本通过 procd 后台运行，有限等待 Docker 与本项目容器，核对 Compose project label 为 `rains` 后才启动；已运行时不重新启动，也不重建镜像/网络。当前系统不带 timeout applet，脚本直接约束自身 Docker 客户端子进程，不依赖安装额外软件。游戏仍由 runtime 的启动期限、磁盘预留和 Docker 的有限重试约束。

`/etc/init.d/rains-ror2 status` 查看容器运行及health；`stop` 暂时停服，`disable` 取消下次开机启动，`enable` 恢复。该服务是一次启动助手，procd实例正常退出不表示游戏已退出。真实路由器上已验证语法、启用链接、容器所有权、对已运行容器的幂等启动和status；目标Linux的故障/所有权模拟测试通过。**尚未执行整机重启或掉电恢复**，不能据此声称完成该项验收。

## 更新与回滚

当前源码 FPTS 维护候选还需要 [精确原生配置](../profiles/native/steam-build-25921972.FPTS.cfg) 和 [overlay 组装](../profiles/README.md)。这份配置只对应本轮 UnityPlayer SHA；官方 1.0.4 DLL 即使使用同一配置也曾实际崩溃，不可直接替换回去。

`tools/native_overlay.py` 会生成 `BepInEx/patchers/Rains.NativeCompatibility.json`。runtime 在晋升目录前及每次启动 Wine 前验证其中的 UnityPlayer、FPTS 和游戏程序集 SHA，以及持久配置中的 GUID、偏移和查找模式。BepInEx 重写注释不影响校验；更新游戏、替换 DLL 或修改地址则需重新审计。没有该元数据的历史候选仍走原有完整文件校验，不能因此认为具有本轮原生兼容校验。

1. 停服并保存 logs、release.json、patch-report.json、Mod lock 和 BepInEx/config。
2. 在电脑生成新原版 snapshot、重新审查 manifest、预制新 runtime；绝不沿用旧 SHA/偏移。
3. 先做兼容验证，再传输路由器。传输中不得启动不完整目录，校验通过后才晋升。
4. 出错时停服并恢复电脑保存的上一完整版本与配置，重新上传并复核。不会复活未验证的 DLL 备份。

镜像标签不是可复现锁：成功实测后记录基础镜像与最终镜像 digest、Debian/Wine 包版本，保留 `docker save` 的归档。apt 安全更新需重建并重新验收。项目当前没有宣称镜像位级可重现。
