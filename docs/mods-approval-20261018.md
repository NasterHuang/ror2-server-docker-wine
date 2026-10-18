# 2026-10-18 Mod 批准记录

晚间随后用户明确批准安装并启用此前推荐的 **Pyroglaive-Faster_Everything 0.1.1**，八项交互加速 true、默认等待上限0.1秒。此授权只增加该服务端插件；配置、固定来源、离线重建、运行证据和回滚边界见 [安装记录](faster-everything.md)。不要求客户端安装，不把插件加载等同于游戏内互动验收。

当日晚间用户追加要求：`On Teleporter Completion Revive=true`、`Auto ping pillars=true`。最新设置与独服自动标记适配见文末；下方最初的 false 配置保留为首批批准记录。

用户已批准仅向软路由独立服务器安装以下组合；Steam 原版客户端不增加 Mod、不修改文件。此前用户已反馈原版客户端可以连接当前服务器。该反馈不构成新增 Mod 的运行验收。

| 项目 | 已批准的版本与行为 |
| --- | --- |
| [TooManyFriends](https://thunderstore.io/c/riskofrain2/p/Moffein/TooManyFriends/) | 1.2.5，服务器人数上限设为 **6 人** |
| [PillarRevive](https://thunderstore.io/c/riskofrain2/p/Thrayonlosa/PillarRevive/) | 1.1.2，队友为死亡玩家的复活柱充能，在当前关复活；**无诅咒、关闭自动标记、关闭柱子额外刷怪、关闭传送器充满自动复活** |

两款 Mod 的批准不是对其他 Mod、客户端安装或全局系统修改的授权。只在现有已运行的 BepInEx / R2API 配置中增加这两款，保留现有固定版本、原生兼容组件和回滚记录。

PillarRevive 的默认配置文件由 BepInEx 插件 GUID `dolso.pillarrevive` 产生：`BepInEx/config/dolso.pillarrevive.cfg`。已批准的最小配置为：

```ini
[_Main]
Enable Mod = true
Curse Stacks = 0
Auto ping pillars = false
On Teleporter Completion Revive = false

[Blood]
Monster Credits = 0

[Design]
Monster Credits = 0

[Mass]
Monster Credits = 0

[Soul]
Monster Credits = 0
```

保留其他未指定设置的上游默认值，包括柱子类型权重和充能时间。`Monster Credits = 0` 关闭的是柱子专属的 CombatDirector 怪物预算，地图原有敌人仍然存在。使用 BepInEx 原生配置格式，UTF-8 文本、英文小写布尔值、十进制数值；不要将这些值写成 JSON 字符串或带引号的配置值。BepInEx 首次运行可能补全默认键与注释，验证应检查对应段与键的实际值，不应要求整个配置文件字节哈希保持不变。

关闭自动标记是独立服务器的必要适配：此 Mod 默认自动标记的实现直接访问第一个本地玩家；无本地玩家的独立服应禁止该路径。玩家仍可使用原版手动标记。

复活柱会在普通关卡新生成，不要求到月球；它使用原版月球柱子的网络对象。玩家需要耗尽原生复活机会且游戏尚未结束，存活队友才能救援；它不阻止团灭结算。关闭“传送器充满自动复活”后，当前关救援依靠柱子，进入下一关的原版复活逻辑仍由游戏负责。

批准前的检查范围：官方包元数据与 manifest、PillarRevive 已编译 IL、现版游戏成员解析与死亡事件 Hook 签名。PillarRevive 59 项 RoR2/R2API 成员引用解析通过；其仅服务器安装的定位同时得到作者页面与原版网络对象复用方式支持。静态检查不等同于实际原版客户端复活成功。

部署后的验收须另行记录：加载日志与实际配置、广告和大厅人数上限、原版客户端加入、死亡产生柱子、充能完成复活、原生复活道具/队友救援交互、换图清理。**5 至 6 个独立客户端同时入服、真实复活、长时多人稳定性、额外延迟和同步表现仍须实际测试；本批准记录不将其记为完成。**

PillarRevive 官方包 SHA-256：`94f44405487cd1f2c98530220d584a255a03d75552abd108f9c13dfcb1e74b34`；DLL SHA-256：`801805422fadcba1877de4c22411c2debeb3a54fb58054ddfb3836916d3b2051`。研究原件位于未纳入版本管理的 `output/revive-research/`，不随源码发布任何游戏程序集或凭据。

独立复核已确认本地候选 `output/mods-server-approved-6` 的 PillarRevive DLL 与上述官方 SHA 一致，配置仅包含上面批准的五个段和八个键，未覆盖柱子权重或充能时间。配置 SHA-256 为 `f30cb75f34993f97781e511b673255767d13951f60f49d6ddd260d4ea2eab300`；本地核查记录为 `output/revive-research/approved-stage-review.json`。这项复核只检查部署候选文件，不表示该组合已在软路由游戏内运行。

## 可维护的离线复现

新锁 `profiles/approved-server-only-6.lock.json` 只固定 10 个官方归档及其依赖，**不是完整可运行 profile**。直接用 `tools/mods.py install` 展开仍会得到已知存在 native ABI 问题的官方 FPTS 1.0.4，也不会带上 V7 的本地源码 overlay、精确 Unity native 配置、ServerTools 和 MMHOOK；不能用裸展开目录替换现有服务。

完整新候选由已纳入源码管理的 [组装工具](../tools/approved_server6.py) 产生；它要求保留的 V7 Mod staging 与离线归档缓存。下面命令从仓库根目录执行，目标必须是新目录：

```sh
python3 tools/approved_server6.py \
  --base output/mods-server-v7 \
  --lock profiles/approved-server-only-6.lock.json \
  --cache output/mod-cache \
  --output output/mods-server-approved-6-rebuilt
```

工具拒绝丢失或被修改的基底清单、错误 native guard/overlay、不同 ServerTools/MMHOOK、依赖版本或 SHA 变化、额外未批准 Mod，以及现存输出目录。基底须为仅含 Mod 及 release 清单的构建产物，不能使用运行中的全游戏目录。缓存包含锁内官方 ZIP 的 `<sha256>.zip` 文件，缺失即失败，工具不下载。它保持基底文件不变，仅加入两款批准 Mod、上述 PillarRevive 配置、`[Game] LobbySize = 6`、来源记录和新的清单；`runtimeVerified` 保持 false。基底丢失后须按主 README 重建源码兼容组件和匹配的 ServerTools/MMHOOK，并重新验证，不能依靠这个官方包锁恢复完整服务。

部署独立于组装：服务器须正常停止后更新 Mod 目录和 release 清单，将这两份配置同步至实际 `runtime/BepInEx/config/` 及 `/opt/ror2/data/bepinex-config/`，同时设 `MAX_PLAYERS=6`。应检查配置目录是否为符号链接；当前手工 overlay 部署中它是实目录，不能假定复制到另一目录即可生效。工具不 SSH、不部署、不启动游戏；新的 assembly 清单通过不替代上文真实多人和复活验收。

2026-10-18 已在另外两个新目录 `output/mods-approved6-reproduced-a` / `output/mods-approved6-reproduced-b` 执行上述工具：全部产物逐文件字节哈希一致，68 项 Mod 清单自洽，批准的配置语义通过，除锁与 release 外基底既有文件均保留原哈希。另验证了“已有输出目录”“清单自洽但换回官方 FPTS DLL”“离线缓存缺失”均拒绝组装，且输入基底没有变化。证据 `output/approved6-repro-verification.json`。此次复现没有修改原候选或已部署文件，也没有运行游戏；新增 provenance 记录使这次复现 release 的 SHA 与先前候选不同，不能据此将运行验收结果转移到新 release。

## 晚间追加：完成传送器复活与独服自动标记

用户明确要求上述两个选项改为 true。最新完整配置为 [pillarrevive-headless.cfg](../profiles/pillarrevive-headless.cfg)。与读取到的服务器实际19项配置逐键比较，只有这两个值变化；无诅咒、6人及额外刷怪预算为0均保留。

官方 PillarRevive 1.1.2 的自动标记直接访问第一个 LocalUser，不能裸启用于本独服。新增独立 [PillarReviveHeadless 兼容组件](../Compatibility/PillarReviveHeadless/README.md)，只替换该 Mod 的 `PingPillar()` 独服路径，固定原版游戏、HLAPI 和 Mod SHA；官方 PillarRevive、现有 ServerTools、FPTS、MMHOOK 及游戏 DLL 均不变。原3秒调度保留，通过死亡玩家持久 Master 的原版 ping SyncVar 发送，不新增网络 prefab/RPC，不要求客户端插件。实际存在完整本地玩家的主机仍使用官方路径；无本地玩家时不会回退到已知空引用。

原版 authority 所有者不会显示服务端给自己的自动标记，因此本适配的接收对象是其他队友；迟加入玩家不保证看见之前的标记。玩家手动 ping 可按原版逻辑替换标记，不持续强制覆盖。转换服可能存在本地网络 client 却没有 LocalUser，所以 setter 的本机 UI hook 仅在调用期间用原版每组件 hook guard 抑制，finally 恢复；原版同步脏位与序列化保持。

复现命令（输出目录为新的本地路径，dotnet 使用本机SDK路径）：

```sh
python3 Compatibility/PillarReviveHeadless/build.py --dotnet /path/to/dotnet --output output/pillar-headless-new-build
python3 tools/pillar_headless_overlay.py \
  --base output/mods-server-approved-6 \
  --build output/pillar-headless-new-build \
  --config profiles/pillarrevive-headless.cfg \
  --output output/mods-server-approved-6-headless-new
```

该 base 为先前完整的 Mod staging，不能是运行中的游戏目录。先用上节 approved_server6 工具重建基础 staging 也可。新增组装工具校验原清单和 V7 原生组件、兼容构建与源码哈希，保留既有文件，仅更新该配置并加入兼容 DLL/来源，重算 release。相同构建输入已两次组装逐文件一致；已有输出和被篡改 DLL 被拒绝，基底未变。新 DLL SHA 为 `80c8bcd6e3ca2fad0aa6186d7cc54969674e32870c6101f4e6709caee66297a7`，Release编译0警告0错误，50项静态检查含35个API引用解析通过。证据 `output/pillar-overlay-verification.json`、`output/pillar-safe-ping-build/audit.json`。

该变更不修复 Boss 圈外交互锁，不改变柱子充能、诅咒或复活流程。加载成功日志和设置读取只能证明组件与配置生效；传送器完成后的真实复活以及其他原版玩家看到标记仍需实际双人测试。
