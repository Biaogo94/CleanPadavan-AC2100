# Redmi AC2100 Padavan Firmware Builder

基于 GitHub Actions 的 **Redmi AC2100** Padavan 固件自动构建脚本。专为追求极致纯净和高性能的用户设计。

## ✨ 特性 (Features)

  * **双版本支持**：启动构建时可选 **3.4 (hanwckf/稳定版)** 或 **4.4 (MeIsReallyBa/新内核版)**。
  * **极致纯净**：自动移除 Aria2、Transmission、各类 VPN 等冗余插件，只保留核心路由功能。
  * **性能优化**：强制开启 **Hardware NAT (Flow Offload)**，确保千兆跑满，降低 CPU 占用。
  * **环境修复**：基于 Ubuntu 22.04，修复了旧版构建脚本在 CI 环境下的依赖和路径问题。

## 🚀 如何使用 (How to Use)

1.  **Fork** 本仓库到你的 GitHub 账号。
2.  进入仓库的 **Actions** 页面。
3.  点击左侧的 **Build Redmi AC2100 Padavan**。
4.  点击右侧的 **Run workflow** 按钮。
5.  在下拉菜单中选择你需要的固件版本：
      * `3.4 (hanwckf)`：无线驱动稳定，适合日常使用。
      * `4.4 (MeIsReallyBa)`：内核较新，支持更多特性。
6.  等待编译完成（约 15-20 分钟），在 **Artifacts** 处下载固件。

## ⚙️ 默认配置 (Default Settings)

  * **管理地址**: `192.168.123.1`
  * **用户名**: `admin`
  * **密码**: `admin`
  * **WiFi 密码**: `1234567890`

## 🛠️ 修改说明 (Customization)

如果需要恢复部分插件，请修改 `.github/workflows/build-padavan.yml` 文件中 `Run Compilation Logic` 下的 `sed` 替换命令：

```bash
# 将 =n 改为 =y 即可启用插件
sed -i 's/CONFIG_FIRMWARE_INCLUDE_ARIA=n/CONFIG_FIRMWARE_INCLUDE_ARIA=y/g' $TEMPLATE_PATH
```

## 🔗 致谢 (Credits)

  * [hanwckf/rt-n56u](https://github.com/hanwckf/rt-n56u)
  * [MeIsReallyBa/padavan-4.4](https://github.com/MeIsReallyBa/padavan-4.4)

-----

**免责声明**: 刷机有风险，请在 Breed 下进行刷写。本仓库仅提供构建脚本，不对固件使用造成的后果负责。
