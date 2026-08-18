# Redmi AC2100 Padavan 3.4 Firmware Builder

本仓库只构建 Redmi AC2100（`RM2100`）的 Padavan Linux 3.4 固件。构建输入、工具链和 HTTPS 依赖均由 Source Lock 固定并校验；构建完成后会验证 uImage 头、CRC、设备型号、内核版本和时间戳，再生成带 SHA-256 的 Firmware Bundle。

## 当前状态

**Release Candidate**。构建和发布工程已建立自动化门禁，但只有填写并通过 [硬件验收记录](docs/HARDWARE-QUALIFICATION.md) 后，某个 Firmware Bundle 才能称为 Production Release。Linux 3.4 和 OpenSSL 1.1.1 均已停止上游支持，部署者必须承担漏洞回补和隔离责任。

## 固件策略

启用：

- RM2100 / MT7621，2.4 GHz `4.1` 与 5 GHz `5.0.5.1` 驱动
- SFE 硬件转发加速
- IPv6、IPSet、中文 WebUI
- 仅 HTTPS 的管理界面

关闭：

- SSH、Telnet、FTP、Samba、VPN、代理、下载器、ttyd
- vlmcsd、socat、srelay、tcpdump、iperf3 等非核心程序
- USB、超频与 CPU sleep 实验选项

完整策略见 [`config/rm2100-3.4.config`](config/rm2100-3.4.config)。任何未批准的 `=y` 选项都会让验证失败。

## GitHub Actions 构建

部署构建只能在私有 fork 中进行。在私有仓库 Secrets 中设置：

- `FIRMWARE_ADMIN_PASSWORD`：16-64 位可打印 ASCII，不能使用通用默认值
- `FIRMWARE_WIFI_PASSWORD`：16-63 位可打印 ASCII，且必须与管理密码不同

运行 **Build RM2100 Padavan 3.4**。普通构建保持 `publish=false`，完成后下载 `rm2100-3.4-<run>-<attempt>` Firmware Bundle。公开仓库的 Actions 会忽略部署 Secrets，始终生成一次性测试凭据；这种产物只用于验证编译，不能部署。

生产发布还需要配置 GitHub `production` Environment 的人工审批规则。workflow 会拒绝从公开仓库发布包含部署凭据的固件；在强制首次启动配置完成前，公开发布不是受支持的生产路径。

## 本地 Linux 构建

安装 `.github/workflows/build.yml` 中列出的 Ubuntu 22.04 依赖，然后：

```bash
umask 077
printf '%s' 'replace-with-strong-admin-password' > /tmp/rm2100-admin
printf '%s' 'replace-with-strong-wifi-password' > /tmp/rm2100-wifi
ADMIN_PASSWORD_FILE=/tmp/rm2100-admin \
WIFI_PASSWORD_FILE=/tmp/rm2100-wifi \
bash scripts/build-firmware.sh
```

默认输出在 `dist/`，包含固件、`manifest.json`、Source Lock、Firmware Profile 和 `SHA256SUMS`。

## 首次部署

- 默认地址：`https://192.168.2.1`
- 管理凭据和双频 Wi-Fi 密码来自本次 Provisioned Build
- 首次启动后再次修改管理密码和 Wi-Fi 密码
- 禁止从 WAN 暴露管理界面
- 使用 Breed 或等价恢复环境，并在升级前导出当前可回滚镜像

生产验收、性能阈值与回滚要求见 [生产门槛](docs/PRODUCTION.md)。

## 上游与许可

- 固件源码：[hanwckf/rt-n56u](https://github.com/hanwckf/rt-n56u)
- 工具链：[hanwckf/padavan-toolchain](https://github.com/hanwckf/padavan-toolchain)

本仓库采用 Apache-2.0；上游源码和各依赖保留其各自许可证。刷写第三方固件存在变砖和数据丢失风险。
