# 雨中冒险 2 游戏服务器：Docker/Wine 实现方案

本项目是《雨中冒险 2》游戏服务器的一种实现方法：对干净的 Windows 原版游戏副本应用精确构建补丁，让它通过游戏已有的服务端代码完成启动和联机，再用 Wine 将这份游戏运行在 Linux 的 Docker 容器中。

[English](README.md) · 简体中文

[![自动检查](https://github.com/NasterHuang/ror2-server-docker-wine/actions/workflows/ci.yml/badge.svg)](https://github.com/NasterHuang/ror2-server-docker-wine/actions/workflows/ci.yml)
[![许可证：GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

## 实现原理

游戏逻辑仍由原版 Windows 可执行文件和 Unity 程序集执行。本项目主要调整这份游戏副本的启动及开服路径：

1. **核对原版，再修改独立副本。** `RoR2Patcher` 先检查原版 `RoR2.dll` 的哈希、方法签名和 IL 位置，再按审核清单打补丁。deferred-server 方案跳过桌面 Steam 客户端初始化代码，使用游戏已有的 dummy user manager，并把真正的 Steam game-server 创建推迟到资源目录加载完成后的正常 `host` 路径；相关网络调用改用服务端实例。
2. **通过 Wine 在 Linux 无图形运行。** Wine 提供 Windows 兼容层，启动器以 `-batchmode -nographics` 启动游戏，并提供 Xvfb 显示环境。Docker 负责封装 Wine 和工具、只读挂载原版来源，以及持久保存准备好的 runtime、配置和 Wine prefix。
3. **适配特定 Unity 与 Mod 组合。** 带 Mod 的配置使用 BepInEx 和按构建核对的兼容组件。维护版 FPTS overlay、Wwise 适配组件分别处理记录中遇到的原生序列化与加载问题；这些组件必须与审核过的游戏和依赖版本匹配。
4. **沿用游戏的真实联机与认证。** 原始构建身份和 Steam 认证检查保持不变，玩家从 Steam 原版游戏连接，无需安装服务端补丁。无法直接连接时，可以用 FRP 中转 UDP；FRP 只负责转发流量，游戏服务器仍由前面的游戏进程承担。

```text
Windows 原版游戏副本 → 审核过的程序集补丁与匹配的兼容组件
                    → Linux Docker 容器中的 Wine / 无图形 Unity
                    → 游戏服务器 ← Steam 玩家（UDP 直连或可选 FRP 中转）
```

因此，这是一套利用原版游戏代码改造启动和开服路径的方案，没有重新实现游戏逻辑或网络协议。部署目标可以是 x86 Linux 主机，也可以是 ImmortalWrt 软路由。代码基于 [albodin/RoR2Server](https://github.com/albodin/RoR2Server)，在其基础上补充了精确构建审查、兼容维护和部署工具。

## 现在能用到什么程度

**目前仍是实验项目。** 已有记录对应 Steam build `25921972`：无 Mod 的原版诊断客户端通过 FRP 进入过大厅，完成了真实 Steam 认证，服务端也启动了第一关。不过，那次使用的是无图形诊断客户端，还不能据此说日常图形游玩或完整多人对局已经稳定。

双人同步、超过四人的实际联机、连续换图、复活和长时间对局，都还需要认真测。后续增加的服务端 Mod 设置也需要单独验证。详细结果和失败记录放在 [测试记录](docs/status.md)。

如果你想折腾家用开服、参与测试，或者研究独服兼容，这里已经有一些能用上的工具。如果你只想复制一条命令就开一个稳定服，目前还需要再等等。

## 仓库里有什么

- **按构建核对的补丁工具**：先检查游戏程序集，再修改明确审查过的位置，保留真实版本信息和 Steam 认证。
- **Docker/Wine 运行环境**：处理启动超时、有限重试、文件校验，以及上一份 runtime 的回滚。
- **固定版本的 Mod 和兼容源码**：当前配置涉及 TooManyFriends、PillarRevive 和 Faster Everything，另有本项目维护的兼容组件。
- **软路由部署工具**：ImmortalWrt 防火墙规则、开机启动助手，以及没有直连公网时可用的 FRP 模板。
- **离线回归检查**：Python 和合成 IL 检查，以及 Linux、Windows 的自动检查流程。

仓库只提供源码和配置模板。游戏本体与 Steamworks 支持文件需要自行合法取得；游戏文件、凭据、运行包和 Mod 二进制不会随仓库发布。

## 怎么部署

先看 **[中文版部署指南](docs/deployment.md)**，里面按准备文件、配置、Docker 启动、软路由单副本部署、玩家连接和回滚的顺序写了步骤。也有对应的 **[英文版](docs/deployment.en.md)**。

```sh
git clone https://github.com/NasterHuang/ror2-server-docker-wine.git
cd ror2-server-docker-wine
cp .env.example .env
```

启动前，还需要按指南准备匹配的原版快照、审查清单、Steamworks DLL 和完整 Mod staging。仅仅构建 Docker 镜像不会自动得到这些东西。Mod staging 的部分组装仍需手工完成；[源码构建说明](docs/building.zh-CN.md) 写清了已有步骤和目前缺少的环节。

玩家正常使用 Steam 原版客户端。局域网连接时，在游戏控制台把下面两个占位值换成自己的信息：

```text
cl_password "YOUR_SERVER_PASSWORD";
connect "YOUR_LAN_HOST:27015";
```

走 FRP 时改用中转服务器的游戏端口。公网端口怎么配置、怎么验证，请按部署指南操作。

## 文档和代码从哪里看

| 入口 | 内容 |
| --- | --- |
| [RoR2Patcher](RoR2Patcher/README.md) | 补丁清单、程序集转换和审查说明 |
| [Compatibility](Compatibility/) | FPTS 维护源码和 PillarRevive 独服适配 |
| [ServerTools](ServerTools/README.md) | 服务端状态观测与 Wwise 兼容组件 |
| [Mod 配置](profiles/README.md) | 包来源锁、配置文件和分阶段组装 |
| [部署指南](docs/deployment.md) | 安装和日常维护 |
| [网络说明](docs/network-performance.md) | FRP、UDP、资源测量和同步排查 |
| [验收清单](docs/validation.md) | 一次完整多人测试应该覆盖哪些操作 |

开发记录中的 `output/` 是本地测试产物路径，不是公开下载地址。早期客户端诊断包仅用于排查问题，当前玩家连接不需要使用。

## 参与开发

离线检查需要 Python 3.11+ 和 .NET 8 SDK：

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

这些检查使用合成数据，不需要专有游戏程序集。提交修改前可以看看 [贡献指南](CONTRIBUTING.md)；分享日志前请先按 [安全说明](SECURITY.md) 删除私密信息。

为兼容已有部署，内部 `Rains.*` 插件标识、`/opt/ror2` 路径和 Compose 项目名 `rains` 继续保留；仓库的描述性名称不会改变这些运行标识。

## 致谢和许可

感谢原 RoR2Server 作者，以及相关 Mod 的作者。项目保留 [GPL-3.0](LICENSE)，仓库内的 FPTS 源码保留 LGPL-3.0 许可，来源记录见 [第三方说明](THIRD_PARTY_NOTICES.md)。《雨中冒险 2》、Steam 和 Unity 的权利属于各自所有者，本项目是非官方的个人开服实验。
