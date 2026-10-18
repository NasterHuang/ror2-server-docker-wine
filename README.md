# RoR2Server：新版 Steam 独立服务器改造

基于 [albodin/RoR2Server](https://github.com/albodin/RoR2Server)，保留 GPL-3.0。目标是在 N5105 / ImmortalWrt / Docker 运行最新 Steam《雨中冒险2》，支持 BepInEx、R2API 和固定版本的 Thunderstore Mod。

部署边界：服务端完全自主运行于软路由，玩家使用官方Steam原版客户端，不要求安装客户端Mod、打补丁、复制游戏或专用启动器。此前客户端包与副本仅作历史诊断；当前连接方法见 [原版客户端测试说明](docs/player-test.md)。默认配置仅采用兼容原版客户端的服务端组件；需要双端安装的内容Mod不作为该配置的前提。

**当前为实验开发版本，尚未验收为可用独立服务器。** 原项目改写版本号、掩盖 Steam 初始化失败的方案已移除。IL 补丁成功、镜像构建成功和 UDP 查询响应，都不代表多人联机成功。

当前进度与失败证据统一记录在 [实际验证状态](docs/status.md)。软路由独立运行服务器与 FRP；经批准已增加 TooManyFriends 1.2.5（6人）及 PillarRevive 1.1.2（无诅咒）。无Mod原版客户端已通过云端 FRP 入大厅及真实 Steam 认证，服务端已启动首关；玩家无需客户端测试包或自定义启动器。目标Linux的90项Python检查通过。超过4人实际联机、真实复活、双人同步、图形操作、换图及占用对局长时稳定性仍未验收；UI和JobTempAlloc等日志仍需检查，不能称为最终稳定版。

## 已落地

- 对用户已更新 Steam build `25921972` 的真实 DLL 做结构审计，原文件 SHA256 `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`。
- 清单锁定 SHA / 方法签名 / IL 偏移，转换前整组检查，独立输出与序列化回读；保留真实 build ID 和版本认证逻辑。
- 原版只读、事务预制、失败回滚、更新漂移拒绝、非 root Wine/Xvfb 运行层、停止信号、有限重启、日志限制。
- Thunderstore 精确版本与依赖 lock、SHA256 / ZIP / manifest 校验、安全离线展开；已迭代至需本地FPTS源码overlay的候选，官方包锁本身不足以复现可启动组合，见 [候选说明](profiles/README.md)。
- 真实软路由 SSH 资源核查；纯净游戏 snapshot 已在电脑生成，原玩家目录未改动。
- 固定 Docker 桥 `br-ror2` 与本项目持久 fw4 zone 已部署、check/reload；显式60 FPS配置已有空大厅资源快照，尚非对局性能基准。
- Python 及合成 IL 回归测试和 CI 配置。真实测试状态随开发记录，见下文。

## 关键边界

当前客户端仍有多条 Steam client singleton 依赖，包括平台初始化、用户/存档/成就、lobby、P2P 和连接检测。现有三项保守补丁不足以证明无 Steam 客户端的完整启动；参见 [补丁审计](RoR2Patcher/README.md)。不会通过伪造 build ID、吞掉初始化错误或关闭版本检查来声称兼容。

当前这台软路由实测约 11.54 GiB RAM，Optane M10 当前可寻址容量为 13.41 GiB；新版游戏单份约 3.84 GiB。已采用电脑保存原版/回滚、路由仅单副本的实验部署，容量复核时 `/opt` 仍有约 1.3 GiB 余量，可继续受控诊断。用户已授权必要时扩容；但 GPT、分区和 ext4 交叉核查确认当前盘无可直接在线扩展的完整 ext4 块，因此没有改分区或 DockerRoot。详见 [容量证据与后续方案](docs/router-assessment.md)。性能、怪物瞬移和公网入服必须实测，不能从配置推导已解决。

## 从这里开始

- [部署、单副本方案和回滚](docs/deployment.md)
- [实际验证状态与当前阻塞](docs/status.md)
- [源码与最新兼容研究](docs/research.md)
- [补丁工具与实际 DLL 审计](RoR2Patcher/README.md)
- [Mod 锁定、候选及客户端要求](docs/mods.md)
- [软路由实测资源](docs/router-assessment.md)
- [网络、FRP、CPU 与同步诊断](docs/network-performance.md)
- [真实多人测试与验收门槛](docs/validation.md)

`profiles/candidate.lock.json` 保留v3候选；[源码overlay专用基础锁](profiles/steam-25921972-source-overlay.experimental.lock.json) 固定官方包来源，其中FPTS1.0.4必须替换，不能直接用于当前Unity。V5与维护版V6均已在Wine取得首次大厅启动结果；V6的正常关闭、再次重启和长时运行仍待验收。不要把游戏、Steam凭据、SSH连接文件、运行数据或密码提交仓库。镜像构建上下文已排除这些文件，游戏文件不进入镜像。

## 重建源码兼容候选

以下分步重建官方基础包、维护版FPTS与精确符号配置；需要Python、已验证的.NET SDK 8.0.426、合法原版游戏及当前UnityPlayer匹配的完整PDB。输出目录必须不存在，PDB需另行按精确身份取得。示例中的路径按实际文件调整：

```sh
python3 tools/mods.py install --lock profiles/steam-25921972-source-overlay.experimental.lock.json --cache output/mod-cache --target output/rebuild-official --download
python3 Compatibility/FixPluginTypesSerialization/build.py --dotnet dotnet --output output/rebuild-fpts
python3 tools/unity_symbols.py --unity-player output/source-25921972/UnityPlayer.dll --pdb output/unity-symbols/UnityPlayer_Win64_player_mono_x64.complete.pdb --fpts-dll output/rebuild-official/BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/FixPluginTypesSerialization/FixPluginTypesSerialization.dll --config-out output/rebuild-fpts.cfg --audit-out output/rebuild-symbols.json
python3 tools/native_overlay.py --base output/rebuild-official --build output/rebuild-fpts --config profiles/native/steam-build-25921972.FPTS.cfg --output output/rebuild-native-overlay
```

符号工具审计的是官方DLL；可用其重新生成配置与已提交配置逐项核对。overlay示例使用已提交的精确配置，仅适用UnityPlayer SHA256 `fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105` 与对应GUID，换Unity必须重审，不能直接沿用偏移。overlay才显式替换为带本地补丁来源的维护DLL。此流程只生成一个候选staging；仍需按现有准备流程组装精确版本MMHOOK、本地Wwise兼容及ServerTools插件、游戏补丁和release清单，再传输校验、启动和验收。它不是一条命令完成部署，也不会把本地替换伪称为官方Thunderstore原包。详情见 [候选与来源说明](profiles/README.md)。

## 本地回归测试

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

这些测试不需要专有游戏 DLL。实际 DLL 的审计、输出、镜像构建日志等保存在忽略提交的 `output/`，只分发补丁源码、清单和工具，不分发游戏程序集。

## 构建与运行

先阅读部署文档，完成精确构建审计与原版导出。复制 `.env.example` 为 `.env`，配置 SHA、密码及明确的实验开关；准备 game/config/mods/data 目录。

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f --tail=200
```

缺少真实来源、审核清单或实验确认时会拒绝启动。默认不是已开箱验收的服务端；`compose.router.yml` 用于电脑已预制且传输校验过的 runtime。

游戏本体、Unity、Steam、BepInEx、R2API 和其它 Mod 各自适用其许可证；本项目的 GPL 不改变第三方或游戏权利。
