# Redmi AC2100 Padavan 3.4 Firmware Builder

本仓库只构建 Redmi AC2100（`RM2100`）的 Padavan Linux 3.4 固件。构建输入、工具链和 HTTPS 依赖均由 Source Lock 固定并校验；构建完成后会验证 uImage 头、CRC、设备型号、内核版本和时间戳，再生成带 SHA-256 的 Firmware Bundle。

## 当前状态

构建和发布工程采用自动化软件门禁，不把机器测试作为发布前置条件。发布产物会经过源码策略、完整编译、镜像完整性和两次干净构建一致性校验；它不代表已经在每台路由器上完成温度、无线或长时间负载验证。Linux 3.4 和 OpenSSL 1.1.1 均已停止上游支持，部署者必须承担漏洞回补和管理面隔离责任。

## 固件策略

启用：

- RM2100 / MT7621，2.4 GHz `4.1` 与 5 GHz `5.0.5.1` 驱动
- 2.4 GHz 与 5 GHz 默认使用澳大利亚 `AU` 地区码，由驱动按 AU 信道、功率限制和设备校准表工作
- 构建时选择 MT7621 启动引导器时钟（默认），或由 3.4 内核强制 `800`、`900`、`1000 MHz`
- SFE 软件快速转发默认使用模式 1；保留 Linux bridge 检查，不启用实验性 bridge ingress bypass
- IPv6、IPSet、中文 WebUI
- 仅 HTTPS 的管理界面

关闭：

- SSH、Telnet、FTP、Samba、VPN、代理、下载器、ttyd
- vlmcsd、socat、srelay、tcpdump、iperf3 等非核心程序
- USB 与 CPU sleep 实验选项

完整策略见 [`config/rm2100-3.4.config`](config/rm2100-3.4.config)。任何未批准的 `=y` 选项都会让验证失败。

## GitHub Actions 构建

运行 **Build RM2100 Padavan 3.4**，在 `cpu_frequency` 选择 `bootloader`、`800`、`900` 或 `1000`。普通构建保持 `publish=false`，完成后下载 `rm2100-3.4-cpu-<mode>-<run>-<attempt>` Firmware Bundle；镜像文件名会明确标记所选模式。公开仓库可直接构建和发布，不需要配置密码 Secrets。

锁定的 3.4 源码会为三个固定频率设置完整 PLL FBDIV 字段，构建器同时验证 Firmware Profile、源码策略和最终内核配置。`bootloader` 是默认且最保守的选择；`1000` 属于可选超频档，可能增加功耗、温度和个体设备不稳定风险。`AU` 地区码不会绕过驱动的法规限制或 EEPROM / SingleSKU 校准；仅应在符合当地法规的部署中使用。

刷机并清空旧 NVRAM 后，AU 默认提供 2.4 GHz 信道 1-13，以及 5 GHz 信道 36-48、149-165；双频 `TxPower` 默认均为 100%，实际射频输出仍受驱动法规表与设备校准限制。SFE 默认值也只在新 NVRAM 上生效，升级保留旧 NVRAM 时应在 WebUI 核对。启动后可从系统日志中的 `CPU/OCP/SYS frequency` 行核对实际 CPU 时钟；不能只凭固件文件名判断运行频率。

RM2100 的 MT7615 路径按上游策略保持硬件 NAT 关闭，使用 SFE mode 1 加速持续 TCP/UDP 转发。模块加载或卸载后会重新读取真实状态；加载失败会恢复 conntrack 参数并写入系统日志。源码决策、未采用的激进参数和测量方法见 [性能与稳定性设计](docs/PERFORMANCE.md)。

正式发布仍通过 GitHub `production` Environment 的人工审批规则。公开默认密码是易用性取舍，管理界面保持仅 LAN HTTPS，SSH 与 Telnet 默认关闭；用户必须在首次登录后修改后台密码和两个无线网络的密码。

## 本地 Linux 构建

安装 `.github/workflows/build.yml` 中列出的 Ubuntu 22.04 依赖，然后：

```bash
CPU_FREQUENCY=bootloader \
bash scripts/build-firmware.sh
```

`CPU_FREQUENCY` 接受 `bootloader`、`800`、`900` 或 `1000`，省略时使用 `bootloader`。默认读取仓库内公开密码文件；高级用户仍可用 `ADMIN_PASSWORD_FILE` 和 `WIFI_PASSWORD_FILE` 指向自定义文件。默认输出在 `dist/`，包含固件、`manifest.json`、Source Lock、实际 Firmware Profile、最终 `kernel-3.4.config`、`performance-profile.json`、`runtime-policy.json`、`build-warning-policy.json` 和 `SHA256SUMS`。

## 首次部署

- 默认地址：`https://192.168.2.1`
- 默认后台用户名：`admin`
- 默认后台密码：`admin`
- 2.4 GHz 与 5 GHz 默认 Wi-Fi 密码：`1234567890`
- 首次登录后立即修改后台密码和两个 Wi-Fi 密码
- 禁止从 WAN 暴露管理界面
- 使用 Breed 或等价恢复环境，并在升级前导出当前可回滚镜像

自动化发布门槛与回滚要求见 [生产门槛](docs/PRODUCTION.md)。如部署者需要额外实机证据，可选用 [硬件验收记录](docs/HARDWARE-QUALIFICATION.md)，它不属于本项目的构建发布门槛。

## 上游与许可

- 固件源码：[hanwckf/rt-n56u](https://github.com/hanwckf/rt-n56u)
- 工具链：[hanwckf/padavan-toolchain](https://github.com/hanwckf/padavan-toolchain)

本仓库采用 Apache-2.0；上游源码和各依赖保留其各自许可证。刷写第三方固件存在变砖和数据丢失风险。
