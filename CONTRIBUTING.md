# 参与开发

本项目针对特定 Steam / Unity 构建开展独立服务器实验。提交问题前，请先阅读 [当前验证状态](docs/status.md) 与 [验收标准](docs/validation.md)。

## 本地检查

需要 Python 3.11+ 和 .NET SDK 8；离线回归用合成数据，不需要游戏本体：

```sh
python -m unittest discover -s tests -v
dotnet run --project RoR2Patcher/tests/Patcher.Tests.csproj
```

Python 检查中的 POSIX shell 和符号链接用例可能在 Windows 上跳过；CI 同时检查 Linux 和 Windows。修改 Docker 部署时，还应执行 `docker compose config --quiet` 和 `docker build -t ror2-ci:experimental .`。

## 提交要求

- 一次变更解决一个具体问题，描述触发条件、修改后的行为和实际执行的验证。
- 游戏更新或 native hook 修改必须重新核对游戏 SHA、Unity PE/PDB、方法签名与 IL；不能直接沿用旧偏移。
- 保留锁文件、上游来源、许可证和本地维护补丁记录。不要直接修改 `Compatibility/FixPluginTypesSerialization/upstream/` 的固定源码。
- 不提交 `.env`、FRP token、SSH 凭据、私人连接信息、原始运行日志、游戏程序集、Mod 二进制或 `output/`。
- 结构测试、插件加载和 A2S 响应各自只证明对应层级。报告多人可用性时需附人数、游戏构建、客户端类型、真实操作、转场和运行时长。

公开 Issue 中只提供已脱敏的最小复现与日志片段。漏洞报告请遵循 [安全说明](SECURITY.md)。
