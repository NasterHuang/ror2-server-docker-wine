# 部署 RainHost

[English](deployment.en.md) · 简体中文 · [项目首页](../README.zh-CN.md)

这份指南介绍项目目前使用的 Docker/Wine 部署流程。记录中的游戏版本是 Steam build `25921972`，更新后的构建需要重新审查。最近的游戏验证记录来自 2026 年 10 月 18 日；发布这份指南没有增加新的实机测试结果。

## 开始前准备什么

目标机器需要是 **x86_64 Linux**，安装 Docker Engine 和 Docker Compose v2。运行的是 Windows Steam 版游戏，通过 Wine 启动。ImmortalWrt 是可选部署目标，也可以使用普通 Linux 小主机。如果服务器同时承担路由工作，建议把大型构建放到另一台 x86 电脑上完成。

正常双副本流程需要容纳镜像、原版游戏、当前和上一份 runtime、Wine prefix 及日志，建议先按 **至少 20 GiB 可用空间** 规划，再核对实际占用。**4 GiB 容器内存上限**只是起始配置，不是实测最低要求；路由和其他服务也需要 CPU、内存和磁盘余量。

此外还需要：

- 合法取得、经 Steam 验证，且程序集与清单匹配的原版游戏。
- 从 SteamCMD app `1007` 正规取得的 Windows x64 Steamworks SDK Redist 支持文件：`steamclient64.dll`、`tier0_s64.dll`、`vstdlib_s64.dll`，以及可选的 `steamwebrtc64.dll`。仅把这些文件放入 `config/steamworks/`，保留来源和哈希记录。App `1007` 提供支持文件，不提供游戏本体。
- 仓库中的 deferred-server 审查清单。
- 若要复现已测试的 Mod 运行路径，需要**完整审核过的 Mod staging**，包括 FPTS 原生 overlay、匹配的 MMHOOK、ServerTools/Wwise 组件、loader 配置和所选 profile，详见 [源码构建说明](building.zh-CN.md)。

**刚克隆的仓库没有完整 Mod staging，也没有可下载即开的游戏镜像。** 部分组装仍需手工完成；如果还没有审核好的 staging，请先补齐它。`MODS_ENABLED=0` 是另一条诊断实验路径，不会复现记录中测试过的 Mod 环境。

## 1. 克隆仓库并创建私有配置

除非特别说明，下面的 shell 命令都在 Linux 构建或部署机器的仓库根目录执行。

```sh
git clone https://github.com/NasterHuang/ror2-rainhost.git
cd ror2-rainhost
cp .env.example .env
chmod 600 .env
mkdir -p config/steamworks mods data output
cp RoR2Patcher/manifests/steam-build-25921972.deferred-server.experimental.json config/patch-manifest.json
```

在 `.env` 中保留 `COMPOSE_PROJECT_NAME=rains`。现有软路由脚本按这个项目名和 `rains-ror2-server-1` 识别容器，仓库目录仍可叫 `ror2-rainhost`。改项目名字不需要搬动 `/opt/ror2`，也不需要更改插件标识。

## 2. 导出并核对游戏

先让 Steam 完成更新和文件完整性验证。在拥有游戏的 Windows 电脑上，用 Python 3.11+ 导出干净副本。下面的 Steam 库路径换成自己的，目标目录必须尚不存在。

```powershell
python tools/snapshot.py --game 'D:\SteamLibrary\steamapps\common\Risk of Rain 2' --target output/source-25921972 --steam-manifest 'D:\SteamLibrary\steamapps\appmanifest_632360.acf'
```

工具不会修改已安装的玩家客户端，也不会导入根目录的旧 loader。把导出快照的**目录内容**传到 Linux 的 `game/` 下：应当直接存在 `game/Risk of Rain 2.exe`，而不是再嵌套一层游戏目录。

```sh
sha256sum 'game/Risk of Rain 2_Data/Managed/RoR2.dll'
dotnet run --project RoR2Patcher -- --inspect --input 'game/Risk of Rain 2_Data/Managed/RoR2.dll' --report output/game-audit.json
```

已提交清单要求的原版 DLL SHA256 是：

```text
48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c
```

如果不一致，先停在这里，重新审查该构建。只替换预期 SHA 不会更新补丁偏移，也不能让新版游戏自动兼容。早期 `experimental`、`server-bootstrap`、`server-networking` 清单用于保留研究过程；本流程采用审核过的 **deferred-server** 清单。

## 3. 放好其余输入文件

目录结构应当是：

```text
ror2-rainhost/
  .env
  game/                         # 原版 Windows 游戏快照
  config/
    patch-manifest.json
    steamworks/                 # 三个必需的支持 DLL
  mods/
    BepInEx/                    # core、patchers、plugins、config 和来源记录
    winhttp.dll
    doorstop_config.ini
    mods-lock.json
  data/                         # 容器用户可写
```

`mods/` 根目录还允许可选的 `.doorstop_version`。组装阶段的根目录 `release.json` 请另行保管，准备流程会生成 runtime 自己的清单。原版 source、Mod staging、支持 DLL 和可写 data 必须互不包含。

首次准备前，将 `profiles/server-config/BepInEx.GUI.cfg` 放入 staging 的 `BepInEx/config/`。一旦生成 `data/bepinex-config/`，后者就是实际持久配置；仅修改 staging 默认值不会覆盖它。更新持久配置前先停服。

编辑 `.env`，填写自己的服务器名和私有密码。完成精确构建审查后，完整 Mod profile 使用以下设置：

```dotenv
COMPOSE_PROJECT_NAME=rains
SERVER_MODE=experimental
ACK_EXPERIMENTAL=1
EXPECTED_GAME_SHA256=48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c
MODS_ENABLED=1
RAINS_SERVER_TOOLS=1
RAINS_RESTORE_CLIENT_WWISE=1
MAX_PLAYERS=6
MEMORY_LIMIT=4g
MIN_FREE_MB=1024
STARTUP_TIMEOUT_SECONDS=600
```

只有安装了匹配的 6 人 profile 才使用 `MAX_PLAYERS=6`，否则按实际 profile 保留人数。Wwise 开关依赖精确审核过的兼容组件，两个插件开关都不能用来掩盖缺少组件的问题。`SERVER_PASSWORD` 请另行填在私有 `.env` 中，不能沿用 `change-me` 示例。密码和服务器名不支持引号、反斜杠、分号和换行。

容器默认 UID/GID 是 `1000:1000`。新建的专用 data 目录可用 `sudo chown -R 1000:1000 data` 赋予写权限。如果使用其他 UID/GID，需同步设置 `PUID`、`PGID` 及目录所有者。原版来源对容器保持只读。

## 4. 构建并启动

第一次测试先把宿主防火墙限制在局域网。Compose 会把三个 UDP 端口发布到宿主，本身不会限制只有 LAN 客户端能访问。

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose logs -f --tail=200
```

正常启动会在独立目录准备 runtime，检查输入、应用补丁、保留上一份 runtime，然后启动 Wine。Linux 下的插件配置保存在 `data/bepinex-config/`。

检查状态：

```sh
docker compose ps
docker compose exec ror2-server python3 /opt/ror2/tools/runtime.py health
docker compose exec ror2-server python3 /opt/ror2/tools/runtime.py query --host 127.0.0.1 --port 27016
```

如果改了查询端口，也要修改命令。启用 ServerTools 后，检查 `data/status/game.json` 的新鲜样本，确认加载、host 和真实 Steam 登录状态。仅有 `boot.json`、UDP 可查询或 Docker 显示 `healthy`，还不能证明玩家能正常游玩。

默认启动期限是 600 秒，进程异常退出最多自动重试三次。仅仅变成 `unhealthy` **不会**触发 Docker 自动重启。

## 5. 空间有限的软路由

在另一台 x86 Linux 电脑，或使用可保留符号链接文件系统的 Linux 虚拟机上准备。输入和 `.env` 与前文一致，然后构建镜像并仅准备数据，不启动游戏：

```sh
docker compose build
docker compose run --rm --no-deps ror2-server prepare
docker save -o output/rainhost-image.tar ror2-local:experimental
tar -cpf output/rainhost-data.tar -C data runtime bepinex-config
sha256sum output/rainhost-image.tar output/rainhost-data.tar > output/rainhost-transfer.sha256
```

若设置了其他 `ROR2_IMAGE`，请替换 `ror2-local:experimental`。上面的归档命令以 Mod 准备流程已经生成 `bepinex-config/` 为前提。将两个归档和校验文件私下传到软路由，核对哈希后用 `docker load -i` 加载镜像。原版和已知可用的回滚副本留在电脑。

对于 `/opt/ror2` 下的**新部署**，放入 Compose 文件、tools、profiles 和私有 `.env`，创建 `game/`、`config/`、`mods/`、`data/`，将验证后的数据归档解到 `data/`，保留符号链接和所有者。以后若要在路由器本地 prepare，还需在对应目录放回精确 config 和支持输入。不要把归档直接解压覆盖到运行中的目录，也不要启动传了一半的 runtime。

```sh
cd /opt/ror2
docker compose -f docker-compose.yml -f compose.router.yml config --quiet
docker compose -f docker-compose.yml -f compose.router.yml up -d
```

该覆盖文件对已准备好的 release 执行 `launch`，不在路由器上重新组装游戏，但仍会在 Wine 启动前校验。算上镜像和 Wine prefix 后，还要保留配置要求的至少 1 GiB 余量。上一版本只在电脑上时，路由器没有本地即时回滚副本。

ImmortalWrt 开机脚本仍使用 `rains` 标识。安装前确认相关路径和容器属于本项目，将 `tools/immortalwrt-boot-start.sh` 放到 `/opt/ror2/deployment/`，将 `tools/immortalwrt-ror2.init` 安装为 `/etc/init.d/rains-ror2`，赋予执行权限，先对启动脚本运行 `--check`，再 enable/start init 服务。它只启动已有容器，不负责创建容器，也不能保证游戏已经就绪。公开记录尚未验证整机重启或掉电恢复。

## 6. 网络和玩家连接

| 用途 | 宿主／容器 UDP 端口 | FRP 公网端口示例 |
| --- | --- | --- |
| 游戏 | 27015 | 28015 |
| A2S 查询 | 27016 | 28016 |
| Steam server | 27017 | 28017 |

Compose 桥名是 `br-ror2`，ImmortalWrt/fw4 可能需要单独的项目 zone。先查看 `sh tools/immortalwrt-firewall.sh status`，再决定是否 `apply`：该操作会允许 WAN 访问三个配置端口。[防火墙与恢复记录](deployment-notes.zh-CN.md) 说明了所有权检查和限制，不要为了让测试通过就改动其他服务的 zone。

使用 FRP 时，从 `profiles/frpc.example.toml` 复制私有配置，填写中转地址和 token，以路由器实际可达的 LAN IP 为本地目标。记录中的宿主部署使用这个地址，而非 `127.0.0.1`。同时检查云端防火墙和 UDP 映射。[网络说明](network-performance.md) 包含现有 procd 服务及来源锁的细节；不要为本项目覆盖或重启共享 frps。

玩家从 Steam 正常启动兼容构建的原版游戏，关闭 crossplay，用 `Ctrl + Alt + 反引号键` 打开控制台，替换私有值后连接：

```text
cl_password "YOUR_SERVER_PASSWORD";
connect "YOUR_LAN_HOST:27015";
```

按上表的 FRP 示例，应改为 `connect "YOUR_PUBLIC_HOST:28015";`。查询结果可能仍公布游戏端口 `27015`，请显式填写外部端口，不要依赖 Steam 浏览器自动选择。

确认真实认证后，再测移动、伤害、拾取、另一名玩家、换图、死亡复活和长时间运行。[验收清单](validation.md) 把这些检查分开列出。10 月 18 日记录证明了单客户端认证和服务端首关启动，尚未证明完整图形多人游玩。

## 更新与回滚

停服、启动和查看日志时，使用同一组 Compose 文件；软路由方案要始终带两个 `-f`。

1. 停止本项目服务器，将配置、日志、`release.json`、`patch-report.json` 和 Mod／来源记录保存到私有存储。
2. 在独立位置构建更新。新游戏哈希和 Unity 偏移先审查，再准备 release；不要在开机时自动更新 Mod。
3. 完整校验传输后，再替换已停服的部署。持久配置应与所选 profile 对应。
4. 更新失败时先停服，恢复上一份完整审核的 runtime **及配套配置**。普通准备流程保留一份 `data/previous`，不能在游戏运行中切换；单副本软路由需从电脑备份恢复。

启动前会检查原生 overlay、release 清单及 Steamworks 支持文件。出现不一致时应找到文件变化的原因，不能修改清单来放行。镜像标签会变化，建议随自己的发布记录保存镜像 ID/digest、包版本、游戏和 Mod 哈希。

`.env`、FRP token、SSH 凭据、连接详情和原始日志不要提交到 Git，问题反馈见 [安全说明](../SECURITY.md)。历史部署观察保留在 [工程记录](deployment-notes.zh-CN.md)。
