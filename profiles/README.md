# 候选 Mod 配置

`candidate.lock.json` 是2026-10-17下载并计算SHA256的 **v3候选**，包含8个包及完整manifest依赖。它保留迭代来源，**不是当前V6源码兼容组合的完整安装清单，也不是已通过联机验收的Modpack**。针对Steam build `25921972`，本地源码候选已完成Mod大厅与Steam后台登录；Mod客户端加入及对局仍未验收。

显式固定的根版本为：

- `bbepis-BepInExPack-5.4.2122`
- `RiskofThunder-RoR2BepInExPack-1.46.0`
- `RiskofThunder-R2API_Core-5.3.0`
- `pseudopulse-SeekersPatcher-1.4.4`
- `score-MiscFixes-1.6.1`

显式根覆盖了依赖 manifest 中部分较旧要求；锁文件仍保留原始要求，方便审计。当前候选是下文 v3；最初依赖已证实失败，其锁保存在 `history/20261017-original-dependencies.failed.lock.json`，仅供复现。R2API_Core 只提供基础模块，后续实际 gameplay Mod 需要的其他模块必须加入候选并重新测试。

```sh
python3 tools/mods.py install \
  --lock profiles/candidate.lock.json \
  --cache output/mod-cache \
  --target output/mods-candidate
```

缓存缺失时可加 `--download`，仍严格要求锁内SHA256。目标目录必须不存在；v3展开目录为 `output/mods-candidate-v3`，旧目录保留证据。`output/`不提交。部署与升级方法见 [Mod文档](../docs/mods.md)。v3曾借助Wwise适配进入Mod大厅，但其FPTS仍失败，不能单独晋升为完整可用组合。

## 实际启动后的候选迭代

原始锁保留作失败复现证据，不能再理解为已验证可用的推荐版本。每次迭代使用新的 `output/` 锁与 staging，完整保留传递依赖及下载 SHA256；以下结构检查不代替真实 loader、客户端和游戏内验证。

- v2：`output/candidate-v2.lock.json`、`output/mods-candidate-v2`。在原有三个显式根之外固定 `pseudopulse-SeekersPatcher-1.4.4`。旧 1.3.7 依赖已经被游戏移除的 `PlayerCharacterMasterController.jumpWasClaimed`，实际 preloader 抛出 `Sequence contains no matching element`。1.4.4 的实际 DLL 明确补回该字段；官方 [版本说明](https://thunderstore.io/c/riskofrain2/p/pseudopulse/SeekersPatcher/v/1.4.4/) 中 1.4.2 记录了相应修复。替换需要保留包内 preloader 和 `SeekersPatcherDLL.dll` 两部分，不能只复制一个 DLL。
- v3：`output/candidate-v3.lock.json`、`output/mods-candidate-v3`。在 v2 根之上固定 `score-MiscFixes-1.6.1`。旧 1.3.8 的 Harmony patch 仅按 `InspectPanelController.Show` 名称选择方法，当前游戏存在重载，在服务器与独立客户端均出现 `AmbiguousMatchException`。1.6.1 实际 DLL 已无该目标引用；[上游固定提交的源码](https://github.com/goldenguy00/MiscFixes/blob/495abede91730a4ec313c76a3115aeac223e9fe8/MysticFixes/ErrorPolice/Legacy/Legacy.cs#L336) 已注释该 patch。这是官方更新移除过时 hook 的证据，不是本项目忽略错误或删除依赖。未发现能据此认定 RoR2BepInExPack 完整替代 MiscFixes 的证据，保留该包。
- v4：`output/candidate-v4.lock.json` 固定官方FPTS `1.0.4`。即便取得当前UnityPlayer精确PDB偏移，旧StringView ABI仍触发native crash，**不得直接按此锁安装后宣称可运行**。
- V5源码诊断候选：固定 [FPTS上游commit](https://github.com/xiaoxiao921/FixPluginTypesSerialization/tree/7b7b2a596c18f1f9bb4ae9ddedfe1eea18cecb7c) 构建DLL SHA256 `43b4ddaeacf2b2350c75851e255ae308257cea7b134e5442814d858104e5551e`，已在Wine完成6插件加载、loadFinished、serverActive、实时SteamLoggedOn及CM connected。证据见 `output/router-v5-boot-2.txt` 和 `output/router-v5-current.txt`。这不证明玩家认证、Mod客户端、多人对局或长时稳定。
- 后续维护候选：同commit上增加names向量保存/恢复及5个delegate保活，DLL SHA256 `1d0ac76ef623cff52b7bbd624bcc22e6fa731c95826a25d1121e6ad2270a5e12`，补丁SHA256 `24651f9460a620a264f42e8239c6f97e352f80fd66e7da6a5de00cc6bf2a9f55`。实际DLL受控内存测试已通过；作为V6部署后，**Wine首次大厅启动已通过**，6插件加载、loadFinished/serverActive/SteamLoggedOn均true，CM connected累计1。正常关闭、再次重启、长时运行及玩家对局仍待验收。

V6镜像为 `284f668f0912`，独立运行证据见 `output/router-v6-game-ready.txt` 与 `output/router-v6-startup-state.txt`，约125秒完成初始化且healthy；不是仅沿用V5结果。目标Linux容器79项Python测试通过（`output/router-v6-linux-tests.txt`），仍不能代替Wine/native hooks执行。

## 本地源码overlay组装

新提交的 `steam-25921972-source-overlay.experimental.lock.json` 是v4官方包的**基础锁**，用于 `tools/mods.py install` 生成overlay输入；不是可直接运行的完整锁。官方包lock负责固定下载来源，不能表达本地维护补丁。使用 [native_overlay工具](../tools/native_overlay.py) 在新目录组装；它要求官方1.0.4 DLL作为精确基底、带 `localPatchesSha256` 的维护构建报告及匹配Unity身份的配置，拒绝覆盖现有目录。完整分步命令见 [主README](../README.md)。以下参数用本地已审查路径替换：

```sh
python3 tools/native_overlay.py \
  --base /path/to/official-v4-stage \
  --build output/fpts-maintained-candidate \
  --config profiles/native/steam-build-25921972.FPTS.cfg \
  --output output/mods-maintained-overlay
```

已提交配置只适用UnityPlayer SHA256 `fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105`，匹配GUID `EEDAE5B1946F4B92AD8D6B3BD79F6C551`；换Unity必须按主README的精确PDB流程重新审计。工具保留原官方DLL为 `.disabled`、复制源码DLL和配置、记录源码/构建/许可证与native兼容元数据；若基底有release.json则同步文件清单和overlay来源。`runtimeVerified` 保持false，组装成功不自动代表部署通过。此CLI面向新的维护候选；此前V5诊断DLL没有维护补丁字段，不应冒充维护构建输入。部署前后仍要按 [实际验证状态](../docs/status.md) 分别记录每一个DLL哈希的真实结果。

2026-10-17 查询 [R2API_Core 官方版本 API](https://thunderstore.io/api/experimental/package/RiskofThunder/R2API_Core/) 时最新版仍为 5.3.0。实际运行报告其构建目标游戏版本 1.4.1，而当前游戏为 1.5.0；此警告必须保留，不能修改游戏版本、认证检查或 R2API 警告来宣称兼容。最终采用哪个锁，应以完整真实测试结果确定。
