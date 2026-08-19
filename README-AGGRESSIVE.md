# ⚠️ EXPERIMENTAL AGGRESSIVE PERFORMANCE BRANCH ⚠️

## 🔥 STOP - READ THIS FIRST 🔥

You are on the **experimental/aggressive-performance** branch. This branch contains **UNTESTED, HIGH-RISK** performance optimizations.

**Read [EXPERIMENTAL-WARNING.md](EXPERIMENTAL-WARNING.md) before proceeding.**

## What Has Been Modified

### 1. CPU - FORCED to 1000 MHz overclock
### 2. Hardware NAT - ENABLED (unstable with PPPoE/VPN)
### 3. SFE - Aggressive mode with bridge bypass
### 4. Conntrack - 65536 (4x increase, OOM risk)
### 5. Wireless - Aggressive BA windows, no protection
### 6. Compiler - O3, LTO, fast-math optimizations

## Expected Improvements (IF STABLE)

| Metric | Baseline | Aggressive | Change |
|--------|----------|------------|--------|
| Routing throughput | ~900 Mbps | ~1100 Mbps | +20-25% |
| CPU usage | ~60% | ~45% | -15% |
| Latency | ~2 ms | ~1.5 ms | -25% |
| Max connections | 16,384 | 65,536 | +300% |
| Temperature | ~75°C | ~85°C+ | +10-15°C |

**These numbers are UNTESTED speculation.**

## Build Instructions

```bash
git clone -b experimental/aggressive-performance \
  https://github.com/Biaogo94/CleanPadavan-AC2100.git
cd CleanPadavan-AC2100

# Review warnings
cat EXPERIMENTAL-WARNING.md

# Build (requires explicit confirmation)
bash scripts/build-aggressive.sh
```

## Testing Requirements

- Serial console access (MANDATORY)
- Breed recovery confirmed
- Temperature monitoring equipment
- Backup firmware ready
- Second router for internet

See [docs/HARDWARE-TESTING-CHECKLIST.md](docs/HARDWARE-TESTING-CHECKLIST.md) for complete testing protocol.

## Legal Disclaimer

This firmware may cause permanent hardware damage. Use at your own risk. No warranty provided.

---

**Status**: ⚠️ UNTESTED - EXTREME RISK ⚠️
