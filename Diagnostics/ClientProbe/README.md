# Rains Client Probe

这是隔离 Windows batchmode 测试客户端的只读诊断插件，不用于玩家正式安装目录，也不应加入服务器 Mod 包。

必须同时设置 `RAINS_CLIENT_PROBE=1`、`RAINS_CLIENT_PROBE_DIR` 为明确的绝对本地输出目录，并使用 `-batchmode` 才会启用。没有默认输出位置；UNC 和网络映射盘被拒绝。插件硬依赖 R2API Core，网络兼容标记允许其他客户端及服务器不安装它。

游戏 `loadFinished` 后，插件在 Unity 主线程每五秒读取实际场景、网络客户端/场景准备状态、NetworkUser 数量、Run 的通关层数与计时，以及现存 CharacterBody/玩家控制/Monster 队伍数量。同目录临时文件通过 `File.Replace` 原子替换 `game.json`。它不修改游戏状态、不运行控制台命令、不注册认证钩子、不记录 Steam ID、账号或令牌。

这些采样可证明测试客户端是否产生了相应的复制对象，不能代替可视化游玩、多人稳定性、延迟、丢包或怪物瞬移的实际验收。

编译使用 .NET SDK：`dotnet build ClientProbe.csproj -c Release`。可通过 `GameManaged`、`BepInExCore`、`R2ApiCore` MSBuild 属性指定现有引用目录，所有外部引用均不复制进输出目录。默认引用当前 build 25921972 原版快照及隔离 Mod 基线。
