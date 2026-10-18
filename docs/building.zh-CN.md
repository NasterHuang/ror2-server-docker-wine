# 源码兼容组件与 Mod staging

[English](building.en.md) · 简体中文 · [部署指南](deployment.md)

这份说明针对 Steam build `25921972`，不是完整安装器。仓库包含 FPTS 原生兼容 overlay 的源码和固定输入，但测试记录使用的完整 V7 staging 是本地构建产物，刚克隆的仓库里没有它。

需要 Python 3.11+、.NET 8 SDK（记录中的编译器是 `8.0.426`）、合法原版游戏快照，以及与该 UnityPlayer 完全匹配的完整 PDB。不同 Unity 二进制之间不能直接沿用偏移。

## 构建原生兼容 overlay

在仓库根目录执行，所有输出目录都必须尚不存在。下面的游戏和 PDB 路径是私有本地输入的示例。

```sh
python3 tools/mods.py install --lock profiles/steam-25921972-source-overlay.experimental.lock.json --cache output/mod-cache --target output/rebuild-official --download
python3 Compatibility/FixPluginTypesSerialization/build.py --dotnet dotnet --output output/rebuild-fpts
python3 tools/unity_symbols.py --unity-player output/source-25921972/UnityPlayer.dll --pdb output/unity-symbols/UnityPlayer_Win64_player_mono_x64.complete.pdb --fpts-dll output/rebuild-official/BepInEx/patchers/RiskofThunder-FixPluginTypesSerialization/FixPluginTypesSerialization/FixPluginTypesSerialization.dll --config-out output/rebuild-fpts.cfg --audit-out output/rebuild-symbols.json
python3 tools/native_overlay.py --base output/rebuild-official --build output/rebuild-fpts --config profiles/native/steam-build-25921972.FPTS.cfg --output output/rebuild-native-overlay
```

符号工具检查的是官方 DLL。组装前，请把生成的配置与已提交配置逐项核对。已提交配置只适用于 UnityPlayer SHA256 `fae6c04f23916263879196211ed241aee5f1f1b53ba4566bb99d4df8526cc105` 及记录中的 PDB 身份。overlay 会明确用维护源码构建替换官方 FPTS DLL，并记录来源。

**如果手上只有这个 overlay，先不要继续部署。** 它只是完整服务端 staging 的一部分，仍需匹配的 MMHOOK、[ServerTools/Wwise 组件](../ServerTools/README.md)、loader 配置和审核后的 release 清单。目前还没有一条受支持的命令，能从全新克隆自动组装全部环节。官方 FPTS 1.0.4 原件曾在记录中的环境崩溃，直接安装官方包锁不能替代这些工作。

## 在已有 V7 基底上追加配置

如果已经有完整审核的 V7 Mod staging 和 release 清单，可以离线组装后续配置。6 人组合的命令是：

```sh
python3 tools/approved_server6.py --base output/mods-server-v7 --lock profiles/approved-server-only-6.lock.json --cache output/mod-cache --output output/mods-server-approved-6-rebuilt
```

`output/mods-server-v7` 是私有构建产物，不是克隆仓库就会生成的目录。缓存必须包含按 SHA256 命名的精确官方归档；工具会核对基底，拒绝用不完整目录代替。重新构建后哈希发生变化，需要重新审查，不能只为了让检查通过就修改预期值。

独服自动标记和 Faster Everything 还有额外的精确输入要求，配置和命令分别见 [profile 说明](../profiles/README.md)、[Pillar 设置](mods-approval-20261018.md) 和 [Faster Everything](faster-everything.md)。

走通用的 `runtime.py prepare` 流程时，`mods/` 根目录只允许 `BepInEx/`、`winhttp.dll`、`doorstop_config.ini`、可选的 `.doorstop_version` 和 `mods-lock.json`。组装阶段的根目录 `release.json` 应另行保管，runtime 准备流程会生成自己的清单。原生兼容元数据保留在 `BepInEx/patchers/` 下。不能只复制几个 plugin DLL，也不能把完整游戏 runtime 塞进 `mods/`。

完整 staging 审查完毕后，再回到 [部署指南](deployment.md)。组装成功得到的仍是候选，之后需要实际启动、客户端连接和游戏内验证。
