# ⚠️ EXPERIMENTAL AGGRESSIVE PERFORMANCE BRANCH ⚠️

## 🔥 WARNING - READ THIS FIRST 🔥

**This is the experimental/aggressive-performance branch with UNTESTED, HIGH-RISK optimizations.**

**This firmware may permanently damage your hardware. Use at your own risk.**

---

## What's Changed

This branch modifies the production-grade [codex/production-grade-3-4](https://github.com/Biaogo94/CleanPadavan-AC2100/tree/codex/production-grade-3-4) branch with **8 aggressive optimizations**:

| Optimization | Change | Theoretical Gain | Risk |
|--------------|--------|-----------------|------|
| **CPU Frequency** | Forced 1000 MHz | +10-15% | Overheating, permanent damage |
| **Hardware NAT** | Enabled | +20-30% | PPPoE disconnects, VPN failures |
| **SFE Mode** | Bridge bypass | +5-10% | Routing loops, firewall bypass |
| **Conntrack** | 65,536 (4x) | 4x connections | Out-of-memory kernel panics |
| **Compiler** | -O3 -flto -ffast-math | +3-8% | Subtle bugs, IEEE 754 violations |
| **Wireless** | BA=64, short GI, no protection | +10-15% | Client compatibility issues |
| **IRQ Affinity** | CPU pinning | +3-5% | Load imbalance |
| **sysctl** | 16MB buffers | +5-10% | Memory exhaustion |

**Expected overall improvement**: +20-40% routing throughput  
**Expected temperature increase**: +10-15°C (may exceed 85°C under load)

⚠️ **These numbers are theoretical speculation without hardware testing.**

---

## Critical Risks

### 🔥 Hardware Risks (Irreversible)
- **MT7621 CPU permanent damage** from overheating (no thermal protection)
- **Device bricking** requiring JTAG recovery
- **Flash memory damage**
- **Shortened device lifespan**

### 🌐 Network Risks
- **PPPoE random disconnections** (known HWNAT issue)
- **VPN protocols failing** (IPsec/L2TP)
- **Wi-Fi client connection failures** (compatibility)
- **Packet loss and kernel panics** under load

### ⚖️ Regulatory Risks
- **Violating FCC/CE RF regulations** (modified TX power, aggregation)
- **Interference with other wireless devices**
- **Legal liability**

### 🔒 Security Risks
- **Firewall bypass** (reduced conntrack checks)
- **Race conditions** in fast path
- **Buffer overflows** from aggressive parameters

---

## Testing Requirements

### Mandatory
- ✅ Serial console access (UART adapter + cable)
- ✅ Breed bootloader recovery confirmed working
- ✅ Known-good firmware backup stored externally
- ✅ Temperature monitoring equipment (thermal camera or thermometer)
- ✅ Second router for internet during testing
- ✅ Understanding and accepting all risks

### Strongly Recommended
- ✅ JTAG adapter for emergency recovery
- ✅ Spare RM2100 device
- ✅ Active cooling (fan pointed at device)
- ✅ Fire extinguisher nearby (seriously - overheated chips can smoke)
- ✅ UPS or stable power supply

### Testing Protocol

1. **Initial Flash** → Monitor temperature immediately
2. **Idle Thermal Test** (30 min) → Abort if > 85°C
3. **Light Load Test** (1 hour) → Single iperf3 stream
4. **Heavy Load Test** (24 hours) → Bidirectional + wireless clients
5. **Stress Test** → Connection flood, memory pressure, thermal limits
6. **Failure Mode Test** → Intentionally trigger edge cases

**At any stage, if issues occur, revert immediately.**

---

## Build Instructions

### Prerequisites
```bash
# Ubuntu 22.04 dependencies (same as main branch)
sudo apt-get install autoconf automake autopoint bison build-essential \
  cmake cpio curl fakeroot flex gawk gettext gperf help2man kmod \
  libgmp3-dev libc-dev-bin libltdl-dev libmpc-dev libmpfr-dev \
  libncurses5 libncurses5-dev libncurses-dev libtool-bin patch \
  pkg-config python3-docutils texinfo unzip vim-common wget xxd zlib1g-dev
```

### Build
```bash
# Clone this branch
git clone -b experimental/aggressive-performance \
  https://github.com/Biaogo94/CleanPadavan-AC2100.git
cd CleanPadavan-AC2100

# Build with forced 1000 MHz CPU
CPU_FREQUENCY=1000 bash scripts/build-firmware.sh

# Output: dist/RM2100_3.4*_cpu-1000mhz.trx
```

### What's Different from Main Branch

The build applies aggressive patches:
- SFE with 5-packet offload threshold and bridge bypass
- IRQ affinity optimization for quad-core
- 64k conntrack, 16MB TCP buffers
- Wireless BA=64, short GI, no protection
- Compiler: `-O3 -march=mips32r2 -mtune=1004kc -flto -funroll-loops`

---

## Configuration Files

- `config/aggressive-performance.json` - Optimization parameters and risk assessment
- `config/rm2100-3.4-aggressive.config` - Aggressive firmware profile
- `tools/generate_aggressive_config.py` - Configuration generator

---

## Comparison with Main Branch

| Aspect | Main Branch | Aggressive Branch |
|--------|-------------|-------------------|
| **Maturity** | ⭐⭐⭐⭐⭐ Production | ⭐☆☆☆☆ Experimental |
| **Reproducible Build** | ✅ Byte-identical | ✅ Maintained |
| **Verification** | ✅ Full gates | ⚠️ Partially bypassed |
| **CPU Mode** | 4 options | Forced 1000 MHz |
| **HWNAT** | ❌ Disabled (safe) | ✅ Enabled (risky) |
| **Temperature** | < 80°C | Possibly 85-90°C |
| **Stability** | High | Unknown |
| **Support** | Community | None |
| **Recommended** | Yes | No |

**Conclusion**: The main branch's conservative approach is well-justified.

---

## Why This Exists

This branch is **NOT for production use**. It exists to:

1. **Explore hardware limits** - Understand MT7621's theoretical maximum performance
2. **Educational value** - Demonstrate risk vs. reward tradeoffs in optimization
3. **Research purposes** - Provide experimental baseline for those with hardware and expertise
4. **Community contribution** - Transparent optimization methodology and risk analysis

If testing proves certain optimizations are safe, they *might* be backported to main branch.

---

## First Boot (Default Credentials)

- **Default address**: `https://192.168.2.1`
- **Default admin username**: `admin`
- **Default admin password**: `admin`
- **Default Wi-Fi password (2.4G & 5G)**: `1234567890`

**⚠️ Change all passwords immediately after first login.**

---

## Recovery Procedure

### Method 1: Breed Recovery (Recommended)
```bash
1. Power cycle into Breed (hold reset during boot)
2. Upload known-good firmware via web interface
3. Select "Clear NVRAM" option
4. Reboot
```

### Method 2: UART Recovery
```bash
1. Connect serial console (3.3V TTL)
2. Interrupt boot (press key during countdown)
3. Upload firmware via TFTP
4. Flash and reboot
```

### Method 3: JTAG (Last Resort)
Requires JTAG adapter and expertise. Dump flash, write known-good image.

---

## Reporting Results

If you test this firmware, please open a GitHub Issue with `[AGGRESSIVE]` prefix including:

- Hardware revision and any modifications (heatsink, etc.)
- Temperature data (idle, load, peak)
- Stability (uptime, crashes, error logs)
- Performance (iperf3 results, CPU usage, latency)
- Issues encountered
- ISP configuration (PPPoE/DHCP/Static, IPv4/IPv6)

---

## Legal Disclaimer

**BY USING THIS FIRMWARE YOU ACKNOWLEDGE AND AGREE:**

1. ✅ This is experimental research software
2. ✅ You accept full responsibility for any damage
3. ✅ The authors provide NO WARRANTY of any kind
4. ✅ You will not hold anyone liable for hardware damage, data loss, or injury
5. ✅ You will comply with local RF regulations (RF output not validated)
6. ✅ You have technical expertise to recover from failures
7. ✅ You will not use in production environments

**IF YOU CANNOT ACCEPT THESE TERMS, DO NOT USE THIS FIRMWARE.**

---

## Upstream & License

- **Original project**: [Biaogo94/CleanPadavan-AC2100](https://github.com/Biaogo94/CleanPadavan-AC2100)
- **Firmware source**: [hanwckf/rt-n56u](https://github.com/hanwckf/rt-n56u)
- **Toolchain**: [hanwckf/padavan-toolchain](https://github.com/hanwckf/padavan-toolchain)

This repository uses Apache-2.0. Upstream sources and dependencies retain their respective licenses.

**Flashing third-party firmware carries risk of bricking and data loss.**

---

## Project Status

- **Created**: 2024-01-20
- **Branch**: experimental/aggressive-performance
- **Status**: ⚠️ Design complete (100%), Hardware testing (0%)
- **Risk**: 🔴 Extreme - May cause permanent hardware damage
- **Support**: None

---

**⚠️ FINAL WARNING: This firmware may permanently damage your device. The main branch is production-grade and sufficient for 99% of users. Only attempt this if you are an experienced embedded developer with proper test equipment and recovery capabilities. ⚠️**
