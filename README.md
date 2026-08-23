# Redmi AC2100 Padavan 3.4 Firmware Builder

本仓库只构建 Redmi AC2100（`RM2100`）的 Padavan Linux 3.4 固件，4.4 内核不在项目范围内。主干同时维护默认性能与激进性能两套配置，并提供两个相互独立的 GitHub Actions workflow。

构建输入、工具链和 HTTPS 依赖由 Source Lock 固定并校验。每次构建都会验证源码策略、Firmware Profile、最终内核配置、uImage 头、CRC、设备型号、内核版本和时间戳，并通过第二次干净构建检查可复现性，最后生成带 `SHA256SUMS` 的 Firmware Bundle。

## 两种构建模式

| 模式 | Actions workflow | CPU 频率 | 转发加速 | 发布类型 |
| --- | --- | --- | --- | --- |
| 默认性能 | **Build RM2100 Padavan 3.4 (Default)** | `bootloader`、`800`、`900`、`1000 MHz` | SFE mode 1；MT7615 路径保持上游 Hardware NAT 默认关闭 | 正式 Release |
| 激进性能 | **Build RM2100 Padavan 3.4 (Aggressive - Experimental)** | 固定 `1000 MHz` | SFE mode 1；强制 MT7621 HW NAT v2 `hw_nat_mode=4`；32K conntrack 与有界队列调优；目标端用户态和库使用 `-O3` | Pre-release |

两个 workflow 文件分别为：

- [`.github/workflows/build-default.yml`](.github/workflows/build-default.yml)
- [`.github/workflows/build-aggressive.yml`](.github/workflows/build-aggressive.yml)

默认性能配置面向通用部署，优先保留上游兼容性。激进性能配置可能提高 NAT 转发能力，但 1000 MHz 强制频率和 Hardware NAT 会扩大温度、PPPoE、VPN、IPv6、Wi-Fi 客户端及重连兼容性风险，不应因为编译成功就视为已经完成硬件认证。

## GitHub Actions

进入仓库的 **Actions** 页面，选择需要的 workflow 后点击 **Run workflow**。

### 默认性能

运行 **Build RM2100 Padavan 3.4 (Default)**：

- `cpu_frequency` 可选择 `bootloader`、`800`、`900` 或 `1000`。
- `release_version` 可留空，自动生成 `YYYYMMDD.<run_number>`；也可手动填写同格式版本号。
- 手动构建成功后，经 GitHub `production` Environment 审批创建正式 Release。
- push、PR 和定时任务只构建并上传 Artifact，不创建 Release。

### 激进性能

运行 **Build RM2100 Padavan 3.4 (Aggressive - Experimental)**：

- CPU 固定为 `1000 MHz`，不提供虚假的其他频率组合。
- 目标端用户态和库从上游 `-Os` 调整为 `-O3`，OpenSSL 增加 `-fomit-frame-pointer`，保留 `mips32r2` / `1004kc` 定向编译。
- 默认连接跟踪数为 `32768`，`netdev_max_backlog=2048`，`somaxconn=1024`。
- 不启用 LTO、`-ffast-math`、循环强展开或 Linux 3.4 不支持的 TCP Fast Open sysctl。
- IPv6 Hardware NAT 保留内核能力但默认关闭，激进默认仅开启 IPv4、Wi-Fi 与 UDP offload。
- 默认 `publish=false`，成功后仅生成 Artifact。
- 如需发布，将 `publish` 设为 `true`，并在 `confirm_risk` 输入 `I_UNDERSTAND`。
- 发布经过独立的 GitHub `experimental` Environment，并强制创建带实验警告的 Pre-release。
- 启动日志和 WebUI 固件版本会显示 `-default` 或 `-aggressive-o3`，用于区分默认性能与激进性能；该标识不改变刷机兼容的基础版本字段。
- push 和 PR 会完整构建两次并校验 Artifact，但不会发布 Release。

默认与激进 Release 使用不同标签命名空间，激进版本带 `aggressive` 标识，不会覆盖或伪装成默认性能版本。

## 固件功能与约束

两种模式共同启用：

- RM2100 / MT7621，2.4 GHz `4.1` 与 5 GHz `5.0.5.1` 驱动
- 2.4 GHz 与 5 GHz 默认使用澳大利亚 `AU` 地区码，实际信道和功率仍受驱动法规表、EEPROM 与 SingleSKU 校准限制
- SFE 软件快速转发 mode 1，并保留 Linux bridge 检查
- QDMA、checksum offload、scatter-gather TX、TSO/TSOv6、RPS 和 XPS
- IPv6、IPSet、中文 WebUI
- 仅 LAN HTTPS 管理界面

默认关闭：

- SSH、Telnet、FTP、Samba、VPN、代理、下载器和 ttyd
- vlmcsd、socat、srelay、tcpdump、iperf3 等非核心程序
- USB、CPU sleep、bridge ingress bypass
- LTO、`-ffast-math`、无限制 conntrack 和法规发射功率覆盖；激进配置使用有界的 32K conntrack 与目标端 `-O3`

完整默认配置见 [`config/rm2100-3.4.config`](config/rm2100-3.4.config)，激进配置见 [`config/rm2100-3.4-aggressive.config`](config/rm2100-3.4-aggressive.config) 与 [`config/aggressive-performance.json`](config/aggressive-performance.json)。任何未批准的选项或不一致的实验声明都会让构建失败。

## 本地 Linux 构建

在 Ubuntu 22.04 安装 workflow 中列出的依赖。

默认性能：

```bash
CPU_FREQUENCY=bootloader \
bash scripts/build-firmware.sh
```

激进性能：

```bash
PROFILE_FILE=config/rm2100-3.4-aggressive.config \
EXPERIMENTAL_PROFILE_FILE=config/aggressive-performance.json \
CPU_FREQUENCY=1000 \
bash scripts/build-firmware.sh
```

默认输出目录为 `dist/`，包含固件、`manifest.json`、Source Lock、实际 Firmware Profile、最终 `kernel-3.4.config`、`performance-profile.json`、`runtime-policy.json`、`build-warning-policy.json` 和 `SHA256SUMS`。激进构建还包含 `experimental-profile.json`，并将其纳入校验和清单。

## 首次部署

- 默认地址：`https://192.168.2.1`
- 默认后台用户名：`admin`
- 默认后台密码：`admin`
- 2.4 GHz 与 5 GHz 默认 Wi-Fi 密码：`1234567890`
- 首次登录后立即修改后台密码和两个 Wi-Fi 密码
- 禁止从 WAN 暴露管理界面
- 升级前准备 Breed 或等价恢复环境，并保存可回滚固件
- 刷写后清空旧 NVRAM，再核对地区码、SFE、CPU 实际频率及 Hardware NAT 状态

公开默认密码是为了方便首次使用，不是安全凭据。固件编译和软件校验通过，也不代表已经在所有硬件个体上完成温度、无线和长时间负载验证。默认模式的部署要求见 [生产门槛](docs/PRODUCTION.md)；激进模式部署前必须完成 [硬件验收记录](docs/HARDWARE-QUALIFICATION.md)。

Linux 3.4 和 OpenSSL 1.1.1 均已停止上游支持，部署者需要承担漏洞回补、管理面隔离和恢复保障责任。性能策略、采用项与拒绝项见 [性能与稳定性设计](docs/PERFORMANCE.md)。

## 上游与许可

- 固件源码：[hanwckf/rt-n56u](https://github.com/hanwckf/rt-n56u)
- 工具链：[hanwckf/padavan-toolchain](https://github.com/hanwckf/padavan-toolchain)

本仓库采用 Apache-2.0；上游源码和各依赖保留其各自许可证。刷写第三方固件存在变砖和数据丢失风险。
