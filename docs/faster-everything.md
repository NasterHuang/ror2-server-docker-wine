# Faster Everything 服务端安装记录

2026-10-18，用户明确批准安装并开启 **Pyroglaive-Faster_Everything 0.1.1**。只部署到软路由独立服，原版 Steam 客户端不安装插件。

来源：[作者页面](https://thunderstore.io/c/riskofrain2/p/Pyroglaive/Faster_Everything/)。作者声明适配 Hallowed Concepts，但只测试过独立无界面启动，完整多人游戏尚未验证。包内只有一个 `FasterEverything.dll`，README 的 “three plugins” 与归档内容不符。

## 配置与来源

已批准配置为 [faster-everything.cfg](../profiles/faster-everything.cfg)：`Maximum delay = 0.1`，打印机、回收器、机会神殿、鲜血神殿、治疗神殿、大锅、净化池、箱子八项均开启。回收器开关也包含无人机回收器。它缩短的是这些交互中的等待，不把传送器、战斗、挑战或 Hallowed 大锅抽取物品节奏改为 0.1 秒。

- GUID：`local.ror2.fastereverything`。
- 实际配置：`/opt/ror2/data/runtime/BepInEx/config/local.ror2.fastereverything.cfg`。
- 持久配置：`/opt/ror2/data/bepinex-config/local.ror2.fastereverything.cfg`。本部署实际为两个文件，须同步修改。
- DLL：`BepInEx/plugins/Pyroglaive-Faster_Everything/FasterEverything.dll`。
- 官方 ZIP SHA-256：`9c438bd063adf211a586f9935b347a5bcbd632ae3fd2569ca1963e69a4152cf1`。
- 官方 DLL SHA-256：`9e2a151edc5a86868c4ea88d795c2f1593674556f689936bc3fe62697a390eba`。
- 新 release SHA-256：`e16fc7795f482e87e8b81e2a6e5ed5f0803ea0870b3db4ae1fc308d63b9ee14d`。

现有 BepInEx、Harmony、RoR2BepInExPack 已满足依赖，没有替换原生兼容组件、游戏 DLL 或现有 Mod。六人上限、无诅咒、两项自动复活/标记设置及额外刷怪预算零保持原值。

## 离线重建

使用 [组装工具](../tools/faster_everything_overlay.py) 和 [固定锁](../profiles/faster-everything-0.1.1.lock.json)。锁只描述官方包来源，不能用裸 `mods.py install` 的结果替换本项目含 FPTS 维护补丁的完整运行目录。

```sh
python3 tools/faster_everything_overlay.py \
  --base output/mods-server-approved-6-headless-ping-v2 \
  --archive output/server-qol-interactables-research/Pyroglaive-Faster_Everything-0.1.1.zip \
  --lock profiles/faster-everything-0.1.1.lock.json \
  --config profiles/faster-everything.cfg \
  --output output/mods-server-faster-everything-new
```

输出必须是新目录。工具固定核对基底 release `a1b8385f…`、完整清单、官方 ZIP/DLL、依赖和新配置，保留旧文件，只增加本插件、配置与来源，并更新 Mod 锁和 release。候选中的 `runtimeVerified=false` 表示组装本身不证明运行验收，实际结果另列下节。

## 部署与回滚边界

部署前新鲜状态为零玩家、无 Run、lobby，Steam 在线，原非配置 Mod 文件 74 项哈希一致。停服后确认只停止项目 `rains-ror2-server-1`，正常退出码 0、无 OOM。备份位于：

`/opt/ror2/deployment/backups/faster-everything-20261018/before.tar`

私有归档包含安装前 release、Mod 锁、运行配置和持久配置，SHA-256 为 `ee10fa3fce6946db0fbf4152bdef629ccb7903040bfca32c895b822378bf2ad2`。上传十个增量文件后已在软路由逐项复核非配置文件及新增配置哈希，再同步持久配置并启动原容器。FRP 没有重启。

需要撤回时先确认空大厅并停止此容器，将新增插件目录、对应 provenance 目录及两份 Faster Everything 配置移出扫描位置；从归档只恢复 `runtime/release.json` 和 `runtime/mods-lock.json`，核验旧组件后启动。不要整体覆盖其他 Mod 的当前配置。该回滚只适用于尚未追加其他 Mod 的本次组合，后续增加插件后应重新组装清单。

## 验证范围

静态检查：当前 build 25921972 的 9 种状态、10 个时间字段、34 个相关成员引用通过，Harmony 依赖匹配。首次启动日志已有 21 条 `Installed:`、插件 loaded，未见该插件缺失目标或安装异常；实际运行配置及持久配置均为八项 true、0.1 秒。

20:16最终验证：新鲜状态为加载完成、serverActive、Steam LoggedOn，healthy、自动重启次数0、空大厅；81个非配置 Mod 文件哈希通过。两份新配置及6人/Pillar设置均通过语义核对。公网 FRP A2S连续3/3成功，返回0/6、lobby；FRP服务没有重启。这证明启动及查询链路，未重新验证实际客户端加入。

当前 R2API_Core 的网络兼容收集只扫描硬依赖 R2API 的插件；本插件没有该依赖，因此不会因缺少 NetworkCompatibility 属性被加入客户端必装名单。RoR2BepInExPack 未发现另一套收集路径；这是本地 IL 控制流核查，不是新增原版客户端入服实测。

本次没有进入游戏测试打印、回收、神殿或开箱，也没有测量性能收益。仅服务端安装时，原版客户端可能保留原动画时长，实际出货/再次交互时间与动画不一致应在联机实测中单独记录。

本地证据：`output/faster-everything-install/`、`output/faster-everything-profile-verification.json`。这些文件不随源码分发，不含客户端改造。
