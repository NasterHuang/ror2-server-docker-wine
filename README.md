# rains · Risk of Rain 2 独立服务器实验

[![离线回归](https://github.com/NasterHuang/rains/actions/workflows/ci.yml/badge.svg)](https://github.com/NasterHuang/rains/actions/workflows/ci.yml)
[![许可证：GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

面向 x86_64 Linux / ImmortalWrt / Docker 的《雨中冒险 2》服务端实验，基于 [albodin/RoR2Server](https://github.com/albodin/RoR2Server)。提供精确 Steam 构建补丁、Wine 运行层、固定版本 Mod 组装、软路由启动恢复与 FRP 配置模板。

**实验版本：已验证单个原版客户端连接及服务端首关启动，尚未完成稳定多人游戏验收，也不是一键部署的成品。** 玩家使用官方 Steam 原版客户端；当前服务端方案不要求玩家安装 Mod、复制游戏或使用专用启动器。

## 功能与范围

- **精确构建补丁**：固定原始 DLL 的 SHA、方法签名及 IL；转换前整组核对，保留真实 build ID 与 Steam 认证，版本漂移时拒绝继续。
- **受控运行**：游戏来源只读、事务准备与失败回滚、非 root Wine/Xvfb、启动超时、有限重启、磁盘余量与日志限制。
- **可追溯 Mod 组合**：Thunderstore 版本及 SHA 锁、离线展开校验、本地 FPTS 维护补丁、精确 Unity PE/PDB 配置和来源记录。
- **服务端组件**：6 人人数配置、PillarRevive 复活及独服标记适配、Faster Everything 交互加速；具体配置与验收边界见 [Mod 文档](docs/mods.md)。
- **ImmortalWrt 部署**：固定 Docker 桥、项目 fw4 规则、procd 启动助手和独立 frpc 服务，支持脱离桌面电脑运行。

## 验证状态

以下是截至 **2026-10-18（Asia/Shanghai）** 的记录，不代表每台设备或后续游戏版本的运行结果。完整历史见 [实际验证状态](docs/status.md)。

| 层级 | 已记录结果 | 仍待验证 |
| --- | --- | --- |
| 单客户端链路 | 无 Mod 原版诊断客户端经 FRP 入大厅，真实 Steam 认证成功，服务端启动首关 | 图形客户端移动、伤害、拾取及完整实体同步 |
| 服务端 Mod | 6 人广告、PillarRevive 及独服标记组件、Faster Everything 加载和配置校验 | 超过 4 人实测、实际复活与标记、交互动画一致性 |
| 部署与恢复 | 软路由独立运行；frpc 单独重启后恢复注册及查询 | 宿主重启、掉电恢复、活动对局中断线恢复 |
| 多人稳定性 | 尚未完成最终验收 | 双人以上同步、多次换图、结算和长时对局 |

容器 healthy、补丁成功、插件加载或 A2S 查询各自只能证明对应层级。测试标准见 [真实多人验收](docs/validation.md)。

## 开始使用

1. 阅读 [部署与回滚](docs/deployment.md)，准备合法原版游戏、Python 3.11+、.NET SDK 8，以及目标 x86_64 Linux 的 Docker Compose。游戏构建必须与审核清单匹配；当前记录基于 Steam build `25921972`。
2. 按 [补丁审计](RoR2Patcher/README.md) 和 [Mod 来源与组装](profiles/README.md) 准备候选。官方包锁还需要本地兼容源码 overlay、ServerTools 和生成的 MMHOOK，不能直接把裸锁输出当作完整可运行环境。
3. 复制 `.env.example` 为本地 `.env`，填写已审核的 SHA、密码及明确的实验开关，准备 game/config/mods/data 挂载。核对设备资源后再运行下方 Compose 命令。
4. 按 [原版客户端连接与测试](docs/player-test.md) 从 LAN 开始验证，再检查公网及多人行为。

```sh
git clone https://github.com/NasterHuang/rains.git
cd rains
cp .env.example .env
# 先按部署文档完成游戏、补丁清单、Mod 和挂载准备，再运行：
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f --tail=200
```

`.env.example` 默认 `ACK_EXPERIMENTAL=0`，缺少真实来源、审核清单或实验确认时拒绝启动。`compose.router.yml` 用于已经在电脑预制并完成传输校验的 runtime；不能跳过准备阶段。

## 仓库导航

| 目录或文档 | 用途 |
| --- | --- |
| [RoR2Patcher/](RoR2Patcher/README.md) | 合成 IL 测试、精确构建补丁及审核清单 |
| [Compatibility/](Compatibility/) | FPTS 维护源码与 PillarRevive 独服适配 |
| [ServerTools/](ServerTools/README.md) | 服务端启动、状态观测及 Wwise 兼容组件 |
| [profiles/](profiles/README.md) | Mod 来源锁、配置模板和分阶段重建说明 |
| [tools/](tools/) / [tests/](tests/) | 快照、组装、运行、网络诊断与离线回归 |
| [docs/deployment.md](docs/deployment.md) | 部署、单副本策略、启动恢复与回滚 |
| [docs/network-performance.md](docs/network-performance.md) | 网络、FRP、CPU 和同步诊断 |
| [docs/router-assessment.md](docs/router-assessment.md) | N5105 实测资源与存储限制 |
| [docs/research.md](docs/research.md) | 兼容研究和历史失败记录 |

文档中的 `output/` 路径指本地诊断产物，未随仓库公开；它们是历史记录的引用，不是可下载附件。历史客户端诊断包和启动脚本仅供研究，当前玩家连接无需使用。

## 开发与检查

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

这些检查使用合成数据，不需要专有游戏 DLL。CI 在 Linux / Windows 运行 Python 回归，在 Linux 检查补丁工具与 Docker 构建。参与方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 重建源码兼容候选

以下分步重建官方基础包、维护版FPTS与精确符号配置；需要Python、已验证的.NET SDK 8.0.426、合法原版游戏及当前UnityPlayer匹配的完整PDB。输出目录必须不存在，PDB需另行按精确身份取得。示例中的路径按实际文件调整：

```sh
python3 tools/mods.py install --lock profiles/steam-25921972-source-overlay.experimental.lock.json --cache output/mod-cache --target output/rebuild-official --download
python3 Compatibility/FixPluginTypesSerialization/build.py --dotnet dotnet --output output/rebuild-fpts
python3 tools/unity_symbols.py --unity-player output/source-25921972/UnityPlayer.dll --pdb output/unity-symbols/UnityPlayer_Win64_player_mono_x64.complete.pdb --fpts-dll output/rebuild-official/BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/FixPluginTypesSerialization/FixPluginTypesSerialization.dll --config-out output/rebuild-fpts.cfg --audit-out output/rebuild-symbols.json
python3 tools/native_overlay.py --base output/rebuild-official --build output/rebuild-fpts --config profiles/native/steam-build-25921972.FPTS.cfg --output output/rebuild-native-overlay
```

符号工具审计的是官方DLL；可用其重新生成配置与已提交配置逐项核对。overlay示例使用已提交的精确配置，仅适用UnityPlayer SHA256 `fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105` 与对应GUID，换Unity必须重审，不能直接沿用偏移。overlay才显式替换为带本地补丁来源的维护DLL。此流程只生成一个候选staging；仍需按现有准备流程组装精确版本MMHOOK、本地Wwise兼容及ServerTools插件、游戏补丁和release清单，再传输校验、启动和验收。它不是一条命令完成部署，也不会把本地替换伪称为官方Thunderstore原包。详情见 [候选与来源说明](profiles/README.md)。

## 许可与安全

本项目保留 [GPL-3.0](LICENSE) 及上游历史；FPTS 固定源码保留其 LGPL-3.0 许可。第三方来源与权利边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本仓库仅发布源码、清单和工具，不分发游戏本体、游戏程序集、Mod 二进制或私人运行数据。`.env`、FRP token、SSH 凭据和私人连接信息应保存在忽略目录；报告问题前请按 [SECURITY.md](SECURITY.md) 脱敏。
