# 公网网络、N5105 资源和同步排查

日期：2026-10-17。以下是实施和实验方案，不是已测性能结论。先完成无 Mod 的真实联机，再逐批加 Mod。

当前真实进展为同 build 单客户端 LAN Mod 大厅认证及服务端首关启动；只读客户端遥测已见同一关卡、玩家控制角色和怪物复制对象。尚未完成可视化操作、双人及公网验收。固定 `br-ror2` 与独立 fw4 zone 已部署并重载；详细规则和移除方式见 [部署说明](deployment.md)。此前自动命名桥未进入 zone 导致 LAN reject，不能由 Docker 自带 ACCEPT 就推断 fw4 已放行。

显式执行 `vsync_count 0; fps_max 60;` 后某次空大厅容器 CPU 为21.95%、内存2.348GiB。此前111.61%来自不同时间的单点快照；这不是同场景重复基准，不能算出性能提升比例，更不能说明怪物瞬移或 RTT 已改善。限帧与物理模拟步长是不同设置，本轮未据此提高 timestep 或网络 tick。

## 公网直连优先

有公网 IPv4 时先测试直连 UDP。游戏端口、Steam query 端口和 Steam server 端口必须固定、互不冲突，并以当前游戏实际监听结果为准。上游默认为 UDP 27015/27016；`STEAM_SERVER_PORT=0` 会引入动态端口的不确定性。容器 `EXPOSE` 只是元数据，不自动开放 WAN 防火墙。

在 Linux 主机执行 `ss -lunp`，检查运行端口；只对选定端口执行限时抓包，例如 `tcpdump -ni any 'udp port 27015 or udp port 27016'`。客户端必须来自另一条外网（例如手机热点或另一家庭网络）；同 LAN 测试可能只验证 NAT 回流。扫描结果 `open|filtered` 不能证明 UDP 游戏握手成功。Steam 列表可见、query 有响应和真正能加入对局分别验收。

Docker bridge 模式检查 WAN 到发布 UDP 端口的转发链，host 模式检查宿主 INPUT。不要混淆两种规则路径。Docker 官方指出 [bridge 网络会创建防火墙规则、host 网络不会](https://docs.docker.com/engine/network/packet-filtering-firewalls/)，并专门说明 Docker 在路由器上可能改变 forwarding policy。先保存当前 fw4/nft/iptables 规则，确认 Docker 启停不破坏 LAN 上网；不要为了游戏开放整个 WAN，也不要盲目关闭 Docker 的 iptables 功能。

公网地址是否真正落在设备 WAN、是否有上级 NAT、ISP 是否阻断 UDP、PPPoE MTU、DNS 指向均需实际检查。Docker Desktop 的 host networking 行为不能替代目标 Linux 路由器验证。

## FRP 为备选路径

FRP [官方 UDP 代理文档](https://gofrp.org/en/docs/features/tcp-udp/)明确支持 `type = "udp"`。对每个实测必须的 UDP 端口建立独立代理，不以 TCP 代理代替。示意片段（不是可直接部署的完整凭据配置）：

```toml
[[proxies]]
name = "ror2-game"
type = "udp"
localIP = "127.0.0.1"
localPort = 27015
remotePort = 27015

[[proxies]]
name = "ror2-query"
type = "udp"
localIP = "127.0.0.1"
localPort = 27016
remotePort = 27016
```

上述 `localIP` 假设 frpc 在宿主或 host 网络中；frpc 在独立 bridge 容器时，127.0.0.1 是 frpc 自己，需要改为正确可达的游戏服务地址。frps 云防火墙和系统防火墙也须允许对应 UDP。若游戏需要额外固定 Steam UDP 端口，按实际监听补齐。服务器公布的地址/端口可能不自动反映 FRP 外部端点，浏览器发现和 console connect 都要实测。

`type="udp"` 与 frpc-frps 的 `transport.protocol` 是两个层次。FRP [官方传输配置](https://gofrp.org/en/docs/features/common/network/network/)提供 TCP/KCP/QUIC 等选项；不能推定换用 QUIC 就降低游戏延迟。先基准直连，再对同一云节点比较 FRP 默认传输和 QUIC，记录额外 RTT、抖动、CPU 与丢包。不要默认开启压缩：它增加 CPU；小包是否受益必须测量。FRP 转发也不保证保留游戏所见的玩家原始源地址。

## 怪物瞬移不是单一网络开关问题

下表是诊断假设，不是对尚未运行实例的因果结论：

| 观察 | 需要采集的证据 | 优先动作 |
| --- | --- | --- |
| 所有玩家同时停顿，之后跳动 | 游戏日志、最忙线程、温度频率、容器 throttling、内存/IO stall | 减少生成物/特效/复杂 Mod；改善散热；避免配额和其他服务争用 |
| 仅一名玩家跳动 | 该玩家 Wi-Fi、RTT/抖动/丢包、客户端帧时间 | 有线对照、换链路；不要先改服务端 tick |
| 上传下载时全员恶化 | 负载下 RTT、WAN 队列及丢包、路由 CPU | 依据实测链路速率配置 SQM；复测 NAT/flow offload 相互影响 |
| 只在某 Mod/新实体出现 | 客服端包及配置 hash、异常栈、内容注册日志、复现录像 | 固定依赖并二分 Mod 集，回到最后通过版本 |
| FRP 才出现 | 直连/中转对照、frpc/frps CPU、两段网络数据 | 换近端线路或用公网直连 |

增大内存可缓解 OOM/换页，但不能保证处理能力。主线程一个核忙满时总 CPU 可能只显示约 25%；Docker CPU 百分比也不是游戏模拟帧时间。Docker 网络 NAT 开销不能未经测量被认定为主要瓶颈。

## 可复现的优化顺序

1. 以 2 人、无 Mod、有线 LAN 建立行为基准，再测外网 2 人及 4 人。保留每次 stage、run 时间、物品和怪物数量条件；不同随机局不能单靠主观比较判断改进。
2. 数据与日志放 SSD/可靠大容量磁盘，避免路由器小闪存。日志限额并轮转；采样从 5 秒开始，调查停顿时短时提高频率。
3. 保留路由、DNS、DHCP、软中断处理余量。先不设置激进 CPU quota/绑核；观察 `/proc/interrupts` 与线程后再做单变量实验。若启用 cgroup 限制，检查 `cpu.stat` 的 throttling；限制太低本身会造成周期性停顿。
4. 用温度与频率记录验证热降频；不直接强制 performance governor 或关闭所有省电机制。16 GB 设备初始为游戏预留约 6–8 GiB 是容量规划假设，最终限额取实测峰值加余量，并保留至少 2 GiB 给路由和宿主；小内存设备相应降低负载。
5. 同时检查 `docker stats`、`docker top`、`/proc/meminfo`、`/proc/pressure/*`（若内核提供）、`dmesg` 中 OOM、`ip -s link`、`ss -s`。BusyBox 命令功能和内核接口可用性以目标机为准；没有指标时写 unavailable。
6. 每次只改变一个变量，重复至少三组相同场景；比较 p50/p95/p99 和最差停顿，而非只看均值。

本项目不提供未经当前游戏反射/源码确认的 `sv_tickrate`、`cl_cmdrate`、网络发送频率或 Unity Fixed Timestep “万能值”。提升模拟频率可能增加 CPU/带宽，单改插值可能掩盖延迟而不修复同步；后续任何同步 Mod 必须先有可复现样本与协议证据。
