# 来源与第三方许可

本项目基于 [albodin/RoR2Server](https://github.com/albodin/RoR2Server)，保留原有 Git 历史及根目录 [GPL-3.0 许可证](LICENSE)。本方案在此基础上增加精确构建审计、实验补丁、Mod 组装、运行验证和 ImmortalWrt 部署工具。

| 组件 | 来源和许可记录 |
| --- | --- |
| RoR2Server 基础代码 | [上游仓库](https://github.com/albodin/RoR2Server)，GPL-3.0 |
| FixPluginTypesSerialization 固定源码 | [上游固定提交](https://github.com/xiaoxiao921/FixPluginTypesSerialization/tree/7b7b2a596c18f1f9bb4ae9ddedfe1eea18cecb7c)，保留 [LGPL-3.0](Compatibility/FixPluginTypesSerialization/upstream/LICENSE)、[来源摘要](Compatibility/FixPluginTypesSerialization/upstream-provenance.json) 和 [本地补丁](Compatibility/FixPluginTypesSerialization/local-patches.json) |
| Thunderstore Mod、BepInEx、R2API | 由 `profiles/` 锁定来源、版本和 SHA；归档及二进制不随本仓库分发，分别遵守各自许可证 |
| FRP | [fatedier/frp](https://github.com/fatedier/frp)，本仓库仅提供来源锁、配置模板和启动脚本 |
| Risk of Rain 2、Unity、Steam | 各自权利人所有；本仓库不分发游戏本体、游戏程序集、UnityPlayer 或 Steam 凭据 |

重新分发衍生构建时，应同时保留对应源码、修改记录和许可证。根目录许可证不改变第三方组件或游戏的权利。
