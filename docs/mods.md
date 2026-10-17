# Mod 锁定、分发与验证

研究日期：2026-10-17（Asia/Shanghai）。以下版本通过 Thunderstore 实时 API 查询，而不是仅依赖搜索引擎缓存。**版本可下载、可安全展开，不等于能在最新 Steam 游戏或专用服务器上运行。** 8 包候选已锁定、下载和展开，并在真实软路由执行首次加载：BepInEx preloader 和 HookGen 已运行，但两个 preloader 插件失败，尚未取得 Chainloader 与 R2API 完整成功加载证据，也未验证玩家客户端兼容性。完整阶段状态见 [status.md](status.md)。

## 当前发现与候选基线

| 包 | 查询结果 | 限制 |
| --- | --- | --- |
| `bbepis-BepInExPack` | `5.4.2122`，发布于 2026-09-06 | Windows Mono / BepInEx 5.4 / Doorstop 4 分发包；不是 Linux 原生 BepInEx 包 |
| `RiskofThunder-RoR2BepInExPack` | `1.46.0`，发布于 2026-10-12 | 比 BepInExPack manifest 中要求的 `1.9.0` 新；升级必须显式固定并实测 |
| `RiskofThunder-R2API_Core` | `5.3.0`，发布于 2025-12-10 | 仍声明依赖 BepInExPack `5.4.2120` 和 HookGenPatcher `1.2.9`；无法据此保证最新游戏兼容 |

R2API 从 5.0 起按功能拆分；只安装实际 Mod 需要的 `RiskofThunder-R2API_*` 模块。不要把历史 `tristanmcpherson-R2API` 单体包当成当前默认。R2API 提供 Mod API，不会自动解决怪物同步或网络延迟。

BepInExPack ZIP 的 `BepInExPack/` 内层内容应与 Windows 游戏 exe 同级。工具对这个包单独处理：只接受内层 `winhttp.dll`、`doorstop_config.ini`、`.doorstop_version` 和白名单 BepInEx 子目录；不会把整个外层包误装到 plugins。Wine 需另外启用原生 `winhttp` DLL override（由启动环境处理）。不要混用 BepInEx 6 / IL2CPP / Linux loader。

## 标准库工具

宿主或构建环境只需 Python 3.9+。实际安装及测试建议使用 Python 3.11+。以下路径均相对仓库根目录。工具不会自动查询“latest”；所有根依赖都必须给定明确版本。

```sh
python3 tools/mods.py lock \
  --package bbepis-BepInExPack-5.4.2122 \
  --package RiskofThunder-RoR2BepInExPack-1.46.0 \
  --package RiskofThunder-R2API_Core-5.3.0 \
  --lock profiles/candidate.lock.json \
  --cache /srv/ror2/mod-cache

python3 tools/mods.py install \
  --lock profiles/candidate.lock.json \
  --cache /srv/ror2/mod-cache \
  --target /srv/ror2/mod-stages/candidate
```

目标目录必须尚不存在。逐一完整验证归档 SHA256 后在相邻临时目录安装，全部成功后重命名成目标目录；失败自动清理临时树。默认离线安装，缓存缺失即失败；只有显式 `--download` 才联网补充缺失 ZIP，并且仍校验锁内 SHA256。在线 lock 步骤将解析依赖、下载并计算真实归档 SHA256，不预填猜测哈希。已有 lock 文件不会被覆盖；更新请生成新文件，经对比和实测后晋升。

依赖解析默认按 manifest 中的精确版本执行；同一包出现不同版本时拒绝继续，并要求给出显式根版本。显式根版本允许覆盖较低依赖要求，但不允许降到任何要求以下；这是一项可审计的人工升级决定，不是兼容性判断。原始 dependency strings 保留在 lock 中。真实 BepInExPack 与 GUI 等包存在循环依赖，解析器支持相同版本的循环共存。不同显式根版本仍会拒绝。

普通 Mod 的 `plugins/`、`patchers/`、`monomod/` 子目录安装到 `BepInEx/<类别>/<Namespace-Package>/`，`config/` 保留预期配置名。直接 DLL 或资源落在该包专属 plugins 子目录。元数据不安装。模组需要其他非标准加载布局时，工具会拒绝核心替换，或保留在 plugins 包目录；应人工审查并扩展受测规则，不能宣称全部 Thunderstore 包均已支持。

工具拒绝 ZIP 穿越、绝对路径、Windows 特殊路径、符号链接和特殊文件、大小写冲突、游戏 exe / UnityPlayer / loader 替换，限制下载及展开体积。除显式可信 BepInExPack 外，包不能写 BepInEx core。目标已有目录（含运行中的游戏目录）拒绝覆盖，避免修改游戏核心或覆盖已调过的配置。SHA256 是首次下载内容的复现校验，不是作者身份或安全性背书；插件仍是任意可执行代码。

## 上线和回滚

1. 保留 Steam depot build ID、游戏文件来源、候选 lock 和服务端配置；禁止正在运行时自动更新游戏或 Mod。
2. 先用同一游戏 build 启动无 Mod 服务器，至少两台客户端验证入服、开局、换图、结算和重连。
3. 在新 runtime 副本中合并新建的 staging（不要覆盖正在运行的目录），先只启用 loader 和必要 API；检查日志中 chainloader、HookGen、R2API 是否成功加载，检查是否有缺方法、程序集冲突或补丁失败。
4. 双端保持同样的 gameplay / content / networking Mod、版本和依赖。需要双方安装的包不能只装在服务器。客户端 UI 包是否能省略，依据对应 Mod 的作者说明和实测；不要盲目使用 IgnoreVersion / DisableNetChecks 绕过兼容检查。
5. 每次只增加一组功能 Mod，重复多人测试。比较相同人数、难度、阶段的帧耗时、CPU、RTT 和丢包；Mod 高负载或日志刷屏可能放大同步问题。
6. 晋升新 runtime 前停止服务并备份配置与必要存档；切换版本目录后启动。异常时切回上一完整 runtime 与其 lock。staging 不自动删除旧插件，不能直接无清理地反复覆盖旧 plugins。

客户端可用相同 lock 和 cache 生成独立的 staging 后审查导入；该 JSON 不是 r2modman profile 导出格式。配置文件和插件生成的数据也需独立同步，包版本一致本身并不代表配置一致。

## 可复现测试与未验证项

```sh
python3 -m unittest discover -s tests -p test_mods.py -v
```

13 项离线单测全部通过，覆盖依赖冲突与显式升级、循环依赖、真实 ZIP 布局模型、完整 SHA256、缓存缺失语义、穿越、符号链接、Windows 路径、大小写冲突、核心保护、体积上限、下载归档完整性与身份及失败清理。

已实际下载 BepInExPack `5.4.2122` ZIP 并验证白名单映射和 staging 展开，归档 SHA256 为 `8a98c3cfa83c920d21c447e0b7606c8a26ab218c35c478394a1fb080efbdb527`。随后完整候选的 8 个包均已下载、固定 SHA256，并成功展开为 `output/mods-candidate`。可提交的锁文件为 [profiles/candidate.lock.json](../profiles/candidate.lock.json)，归档缓存位于被 git 忽略的 `output/mod-cache`。

在线下载遇到过 CDN TLS `UNEXPECTED_EOF_WHILE_READING` 和一次截断 ZIP。有限重试与系统 PowerShell HTTPS 下载补齐归档后成功完成；没有绕过证书校验。锁定阶段现会额外校验 ZIP 和 manifest 中的包名、版本，避免把截断内容锁成合法包。完整候选的实时 API 解析发现并修复了循环依赖处理。此结果证明候选依赖已完整获取和可安全展开，仍不代表游戏已成功加载。

首次真实加载证据为 `output/router-mod-loader-diagnostic-3.txt`：BepInEx `5.4.21.0` preloader 运行，HookGen 完成生成，但 `pseudopulse-SeekersPatcher-1.3.7` 对当前程序集字段匹配失败（`Sequence contains no matching element`），FixPluginTypesSerialization 在下载匹配UnityPlayer的PDB时因 `TLS Support not available` 初始化失败。SeekersPatcher官方发布的 `1.4.4` 为升级研究候选，尚未取得本设备运行结果；PDB路径亦待修复及复测，不能因为 preloader finished 就视为插件均成功。

该失败期间容器仍显示 `healthy`，A2S查询健康不检查 Chainloader/R2API 成功状态。游戏 Mod ABI、N5105性能、多人同步和长时稳定性仍需部署环境验收，不能由下载、HookGen输出或A2S健康推导完成。

## 一手资料

- [Thunderstore BepInExPack 实时包 API](https://thunderstore.io/api/experimental/package/bbepis/BepInExPack/) 与 [固定版本 API](https://thunderstore.io/api/experimental/package/bbepis/BepInExPack/5.4.2122/)：版本、时间、manifest 依赖。
- [Thunderstore RoR2BepInExPack 实时 API](https://thunderstore.io/api/experimental/package/RiskofThunder/RoR2BepInExPack/)：查询得到 `1.46.0`，搜索缓存仍可能显示 `1.9.0`。
- [Thunderstore R2API_Core 实时 API](https://thunderstore.io/api/experimental/package/RiskofThunder/R2API_Core/)：模块最新版本与依赖。
- [BepInExPack 作者安装说明](https://old.thunderstore.io/c/riskofrain2/p/bbepis/BepInExPack/)：内层包布局、Doorstop 4、BepInEx 5.4。
- [R2API 项目 README](https://github.com/risk-of-thunder/R2API)：5.x 功能模块依赖方式。
- [RoR2BepInExPack 源码](https://github.com/risk-of-thunder/RoR2BepInExPack)：版本修复说明和更新审查。
