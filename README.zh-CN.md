# RainHost

**给《雨中冒险 2》找个能一直开着的家。**

[English](README.md) · 简体中文

[![自动检查](https://github.com/NasterHuang/ror2-rainhost/actions/workflows/ci.yml/badge.svg)](https://github.com/NasterHuang/ror2-rainhost/actions/workflows/ci.yml)
[![许可证：GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

RainHost 想做的事很简单：让家里的 Linux 小主机或 x86 软路由负责开服，自己的游戏电脑关机后，服务器还能继续运行。朋友从 Steam 正常启动《雨中冒险 2》就能连接，不用另外装一套客户端整合包。

服务端通过 Docker 和 Wine 运行。这个仓库主要处理开服时那些麻烦的地方：没有桌面 Steam 客户端时怎么启动、游戏更新后怎样判断补丁还能不能用、Mod 怎么固定版本，以及服务器出问题时怎么查、怎么退回上一版。

项目从 [albodin/RoR2Server](https://github.com/albodin/RoR2Server) 改起，保留了上游历史，也加入了针对具体游戏构建的补丁、兼容组件、Mod 配置和 ImmortalWrt 部署工具。

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
git clone https://github.com/NasterHuang/ror2-rainhost.git
cd ror2-rainhost
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

项目之前叫 `rains`。现有 `Rains.*` 插件标识、`/opt/ror2` 路径和 Compose 项目名 `rains` 继续保留，避免改个名字就影响已经部署的服务。

## 致谢和许可

感谢原 RoR2Server 作者，以及相关 Mod 的作者。项目保留 [GPL-3.0](LICENSE)，仓库内的 FPTS 源码保留 LGPL-3.0 许可，来源记录见 [第三方说明](THIRD_PARTY_NOTICES.md)。《雨中冒险 2》、Steam 和 Unity 的权利属于各自所有者，本项目是非官方的个人开服实验。
