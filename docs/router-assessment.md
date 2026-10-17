# 目标软路由只读评估

检查日期：2026-10-17（Asia/Shanghai）。已通过用户提供的 SSH 连接信息进行真实远程检查。仅执行读取命令；未改路由、防火墙、分区、现有容器或系统服务。连接文件仅作为连接数据解析，未执行其中内容。账号密码没有写入脚本、报告或命令行。

## 结论

**CPU 架构与 Docker 适用，当前可用存储不足以按“空间充足”规划完整部署。** 候选工作目录为 `/opt/ror2`，但本轮未创建。必须先量取合法游戏来源、运行副本、镜像展开、Wine prefix、Mod 和日志的实际总容量，再决定是否能放入现有剩余空间；不应直接在生产路由上构建完整镜像。

## 实测环境

| 项目 | 读取结果 |
| --- | --- |
| 系统 | ImmortalWrt 25.12.1，revision r37978-cd0a06bfd3fd |
| 内核/架构 | Linux 6.12.94，x86_64 |
| CPU | Intel Celeron N5105，4 核/4 线程 |
| 内存 | MemTotal 12,103,928 KiB，约 11.54 GiB；首次采样 MemAvailable 约 9.78 GiB |
| Swap | 未配置 |
| Docker | Engine 27.3.1，Linux x86_64，cgroupfs / cgroup v2 |
| Compose | Docker Compose v5.1.4 |
| Docker 数据目录 | `/opt/docker` |
| 根目录 | ext4，约 2.0 GiB，总可用约 1.46 GiB |
| `/opt` | ext4，总计约 11.1 GiB，剩余约 7.11 GiB；与 `/opt/docker` 为同一块分区 |
| 物理存储 | 仅识别一块 NVMe，INTEL MEMPEK1J016GAL，整盘约 13.41 GiB；分区已覆盖几乎整盘，没有发现额外大容量盘或可用未分配空间 |
| 运行中容器 | 6 个；没有停止、重启或更改 |
| CPU 竞争 | 首次采样一个既有容器约 93% CPU（约一核）、750 MiB 内存；其余容器 CPU 接近空闲。瞬时采样不代表持续平均 |
| 宿主负载 | 约 1.2 / 1.2 / 1.2，运行约 11 天；仍需长时采样 |
| WAN | 默认路由为 `pppoe-wan`，接口 IPv4 经本地分类为全局地址；报告不保存具体地址 |

`/tmp` 的约 5.8 GiB 是 tmpfs，消耗 RAM，不能当作持久额外磁盘；所有 Docker overlay 挂载也不是独立容量。`du` 遍历 Docker overlay 可能重复计算，因此容量预算以 `df` 和实际镜像占用为准。

## 资源和部署建议

1. 若需要保留原始来源、独立运行副本及旧版本回滚，现有约 7.1 GiB 可用空间很可能不足；尚未读取实际游戏大小，不能给出可部署结论。建议增加可靠 SSD/USB 大容量存储并挂载后再部署。此次没有进行任何扩容或迁移。
2. `/opt/ror2` 是目前合理的持久候选位置；根目录空间小，不选 `/root`。若新增存储，改用其专用目录，避免与已有 Docker 容器争抢 `/opt`。至少保留 2 GiB 或分区 15%（取较大者）给系统/现有服务，是本项目容量目标，不是硬件保证。
3. 先在 Windows/另一台 Linux 构建纯运行环境镜像，量取镜像加载后的空间后再导入。游戏文件不应打入镜像；否则重复来源、镜像层和运行副本会放大占用。
4. RAM 足以开始轻负载实验。现有约 11.5 GiB RAM 不宜直接分配游戏 8 GiB；初次可从 4 GiB 容器上限、默认 2–4 人和轻 Mod 集观测，确认峰值/失败模式再调整。容量不足时不得靠高频重启掩盖 OOM。
5. 宿主已有约一核竞争，先不强制绑核或停既有容器。记录最忙游戏线程、路由吞吐及 cgroup throttling；即使总 CPU 未满，游戏主线程也可能饱和。

## 诊断工具边界

读取确认可用 `netstat`、`curl`、`wget`、`nft`、`iptables`。未发现 `ss`、`tcpdump`、`python3`、`findmnt` 的命令路径；`lsblk` 没有输出。后续端口检查优先使用 `netstat -lunp`；包捕获等需另行提供工具，不应将工具缺失解读为端口未监听。此次未查看防火墙完整规则或进行 WAN 握手，没有验证游戏端口可达。

## SSH 主机身份

首次连接采用 TOFU，将服务器公钥保存到本地 `output/known_hosts`，后续连接校验该记录，密钥变化会拒绝连接。指纹：`SHA256:QitT17ZV4DvcCstli26GwUlEVHB6secWGC8hzR0aq/c`。这是首次观察到的身份，未通过其他可信渠道独立核验。报告不包含密钥正文或主机私有地址；`known_hosts` 含连接地址与公钥，应仅保存在本地，不提交公开仓库。

## 尚未验证

Docker 镜像构建/加载、真实游戏文件传输、Wine/BepInEx 启动、补丁对该游戏构建的兼容性、UDP WAN 可达、Steam 浏览器与握手、多人对局、长期性能均未由此次只读检查验证。公网接口地址属于全局地址也不等于 ISP 或防火墙允许入站游戏流量。

## 后续授权的单副本部署准备

在后续部署授权下，已对 PC 游戏树排除 `Mods`、`r2modman`、`winhttp.dll`、`doorstop_config.ini`、`.doorstop_version` 后精确计数：2,777 文件，4,122,346,118 字节（约 3.839 GiB）。只排除这些目录不能证明 DLL 经 Steam 验证完整；完整性仍由原版快照流程负责。原始来源和回滚保存在 PC，路由仅放 PC 预制运行副本，可避免两份游戏文件占用超过现有剩余空间。

基础镜像构建前，以运行副本 3.839 GiB、镜像预算 1,200 MiB、Wine prefix 800 MiB、Mod/日志 200 MiB 及最低 1 GiB 剩余空间进行门禁，计算可开始基础镜像构建；这些仍是规划预算，需构建后实际测量再次确认。已创建 `/opt/ror2/build-base` 并上传仅属于本项目的 Dockerfile，使用 Debian bookworm-slim 与 nonroot UID/GID 1000。未传输游戏文件、启动游戏或更改已有容器/网络。

构建日志和容量结果分别保存在本地 `output/router-base-build.log`、`output/router-base-build-result.json`（后者仅在构建成功后产生）；若结果文件不存在，不能宣称构建完成。

基础镜像已构建成功：`ror2-runtime-base:bookworm-local`，镜像 ID `sha256:75a8e6bb36f728feb4771e119a207c132f6deb54342b6f91b2e75455c1099c35`，Docker 报告大小 1,099,123,223 字节。构建前后 `df` 可用空间从 7,635,030,016 字节降到 6,167,445,504 字节，净变化 1,467,584,512 字节；这是采样期间的宿主整体变化，包含并发服务/其他本项目传输影响，不能全部归为镜像独占物理空间。

按本分支保守预算再扣除运行副本、800 MiB prefix 与 200 MiB Mod/日志后，预计余量为 996,523,386 字节，低于 1 GiB 门槛，因此本分支停止进一步传输/部署。主协调分支已另行并行传输无 Mod 运行副本用于启动诊断，将负责以实际 prefix 和实时剩余空间复核；这不改变本报告的门禁未通过事实。

基础环境 smoke 已通过：新建一次无网络、自动移除的本项目临时容器，确认 `uid=1000` / `gid=1000`、Python 3.11.2、Wine 8.0、Xvfb/xauth 存在且 `/data` 可写。此 smoke 未初始化 Wine prefix、未运行游戏、不证明 Steam/Unity/Mod 联机兼容。证据见 `output/router-base-smoke.json`。

## 分区与 ext4 容量复核纠偏（后续只读检查）

用户指出标称 16 GB Optane M10 可能存在可供 Docker 扩容的空间，因此重新核查块设备 sector、GPT 分区边界、真实 mountinfo 和 ext4 superblock。**此前仅凭 `df` 与分区列表判断的依据不完整；本次已补足文件系统是否未扩展、保留块及 bind mount 的验证。** 没有执行分区写入、`resize2fs`、`e2fsck`、卸载或 Docker 迁移。

| 对象 | 读取结果与含义 |
| --- | --- |
| 整盘 namespace | `/sys/class/block/nvme0n1/size` 为 28,131,328 sector，每 sector 512 字节，总计 14,403,239,936 字节（13.414 GiB）；这是当前操作系统实际可寻址容量，不以包装标称 16 GB 替代 |
| p2/root 分区 | start 66,048，end 4,260,351，共 4,194,304 sector，2,147,483,648 字节 |
| p3/opt 分区 | start 4,261,888，end 28,131,293，共 23,869,406 sector，12,221,135,872 字节 |
| GPT 尾部 | 只读解析 GPT 主头：last_usable_lba = 28,131,294，backup_header_lba = 28,131,327；p3 后仅余 1 个可用 sector（512 字节），再后 33 sector 为备份分区表及 GPT 头。该 512 字节加分区内不足整块的 3,072 字节仍不足一个 4,096 字节 ext4 块 |
| p2/p3 间隙 | 1,536 sector，即 786,432 字节（768 KiB）；位于 p3 之前，不能直接增大末端，也不足以形成有意义扩容 |
| p3/ext4 | magic 0xEF53，block_size 4,096，block_count 2,983,675，文件系统 12,221,132,800 字节；与分区仅差 3,072 字节，不足一个块，已经扩展到分区允许大小 |
| p3/ext4 保留块 | reserved_block_count = 0，无可通过降低 root reserved percentage 回收的空间 |
| p2/ext4 | block_size 4,096，block_count 524,288，文件系统 2,147,483,648 字节，与 p2 完全相等；reserved_block_count = 0 |
| 真实根挂载 | mountinfo 设备 `259:2` 对应 p2，挂载到 `/`；`/dev/root` 字符名称不表示另一个可扩磁盘，且该路径没有普通设备节点 |
| DockerRoot | `/opt/docker` 的 mountinfo 为 `259:3`、文件系统内部根 `/docker`，即 p3 上的子目录 bind mount；它与 `/opt` 共用同一个 ext4 容量池，不是一个较小的独立 Docker 分区 |

宿主缺少 `tune2fs`、`dumpe2fs`、`sfdisk`、`blockdev`；可用 `resize2fs`、`e2fsck`、`fdisk`、`parted`、`partprobe`、`losetup`。因此只读读取 p2/p3 各自偏移 1,024 字节处的 1,024 字节 ext4 superblock，在 PC 内存按 little-endian 字段解析；原始 superblock 未输出或保存。已挂载文件系统的 superblock free count 可能落后于内核计数，当前可用空间使用 `df`，未用旧 free count 推算“额外空间”。本次复核时 `/opt` 实时可用约 1.312 GiB，数据会随现有服务与游戏诊断变化。

**可明确获得的原盘在线扩容容量：0 个完整 ext4 块。** 这不是根据 `df` 推断，而是分区几何与文件系统大小的交叉结论。原盘 root 中另有约 1.46 GiB 可用，但那是 p2 上已格式化文件系统的剩余容量，不会自动加给 DockerRoot。

可维护的方案按风险排序：

1. 当前约 1.3 GiB 余量足够继续受控诊断；保持日志限额和实时容量门禁，按真实 Wine prefix 峰值决定保留状态。本次不为扩容更改任何系统设置。
2. 真正需要更多持久容量时，增加独立可靠 SSD/USB 存储，将本项目运行副本、prefix 和日志放到新增存储；保留 DockerRoot 及既有容器不动。只迁移本项目的数据并修改其挂载最容易回滚。
3. 若必须利用 p2 的部分空闲，可把本项目某个独立、可限额目录放在 p2（例如少量日志或经实测较小的 prefix），再单独 bind mount；这不是分区扩容，并须为固件、升级及系统日志保留充足余量。不能把整个 `/opt/docker` 指向 root，也不能让无界日志挤满系统根分区。此方案尚未实施。
4. 将 p2 容量转给 p3 需要离线缩小 ext4 p2、缩小其分区并移动 p3 起始位置及数据；`resize2fs` 不能单独移动现有 p3 的起点，且 ext4 不能在线缩小。这涉及系统与所有现有 Docker 数据，须有离线完整盘备份、救援启动和维护窗口，收益仅约根目录可释放部分，当前不推荐。不要在运行中的生产路由尝试删除重建 p3 来“扩容”。

完整脱敏读数保存在 `output/router-storage-verification.json`，包括 sector、superblock 字段、工具可用性和 mountinfo。没有更改分区、ext4 参数、DockerRoot 或现有服务。
