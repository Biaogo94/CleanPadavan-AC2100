# ⚠️ EXPERIMENTAL AGGRESSIVE PERFORMANCE BRANCH ⚠️

## 🔥 CRITICAL WARNING - READ BEFORE PROCEEDING 🔥

This branch contains **UNTESTED, AGGRESSIVE performance optimizations** that may:

### HARDWARE RISKS
- ❌ **Overheat and permanently damage your MT7621 CPU** (no thermal protection)
- ❌ **Brick your device** requiring JTAG/serial recovery
- ❌ **Damage flash memory** through excessive writes
- ❌ **Reduce device lifespan** through sustained high temperatures
- ❌ **Void warranty** (if applicable)

### NETWORK RISKS
- ❌ **PPPoE/VPN connections may randomly disconnect**
- ❌ **Wi-Fi clients may fail to connect or experience dropouts**
- ❌ **Packet loss under high load**
- ❌ **Routing loops or forwarding errors**
- ❌ **Out-of-memory kernel panics**

### REGULATORY RISKS
- ❌ **May violate FCC/CE/local RF regulations** (modified TX power/aggregation)
- ❌ **Interference with other wireless devices**
- ❌ **Legal liability for unauthorized RF emissions**

### SECURITY RISKS
- ❌ **Bypassed connection tracking checks** (potential firewall bypass)
- ❌ **Race conditions in fast path**
- ❌ **Exploitable buffer overflows** from aggressive parameters

## WHAT HAS BEEN MODIFIED

1. **Hardware NAT (HWNAT) - ENABLED**
   - Bypasses software flow control
   - Known issues with PPPoE, IPv6, and some VPN protocols
   
2. **CPU Frequency - FORCED TO 1000 MHz**
   - Overclocked beyond safe limits for some chips
   - No voltage/thermal margin
   
3. **Aggressive SFE Parameters**
   - Offload threshold reduced to 5 packets
   - Bridge ingress bypass enabled (EXPERIMENTAL upstream feature)
   
4. **Increased Connection Limits**
   - 65536 conntrack entries (4x default)
   - May cause OOM on 128MB device
   
5. **Aggressive Wireless Settings**
   - Increased AMPDU/AMSDU sizes
   - Reduced protection intervals
   - May cause client compatibility issues
   
6. **Compiler Optimizations**
   - Link-time optimization (LTO)
   - Aggressive inlining
   - May introduce subtle bugs
   
7. **IRQ Affinity Tuning**
   - Pinned to specific cores
   - May cause unbalanced load
   
8. **Reduced Memory Safety Margins**
   - Lowered watermarks
   - Disabled some kernel debugging

## PREREQUISITES FOR TESTING

### Required
- [ ] Second working router for internet access during testing
- [ ] Serial console access (UART adapter + cable)
- [ ] Breed/U-Boot recovery environment confirmed working
- [ ] Known-good firmware backup stored externally
- [ ] Ability to disassemble device for emergency recovery
- [ ] Temperature monitoring equipment (thermal camera or thermometer)
- [ ] UPS or stable power (do NOT test during storms)

### Recommended
- [ ] JTAG adapter for emergency recovery
- [ ] Spare RM2100 device
- [ ] Fire extinguisher nearby (seriously)
- [ ] Thermal pads/heatsink upgrade installed
- [ ] Active cooling (fan) pointed at device

## TESTING PROCEDURE

1. **Prepare Recovery**
   - Backup EEPROM
   - Backup current firmware
   - Test Breed recovery before flashing
   
2. **Initial Flash**
   - Flash this firmware
   - **IMMEDIATELY watch temperature** - if > 80°C, power off
   - Monitor serial console for kernel panics
   
3. **Thermal Testing (30 minutes)**
   - Run iperf3 bidirectional test
   - Monitor temperature every 60 seconds
   - **If > 85°C, ABORT and revert**
   
4. **Stability Testing (24 hours minimum)**
   - Sustained traffic test
   - Multiple concurrent connections
   - Wi-Fi client roaming test
   - PPPoE reconnection test
   - Monitor system logs for errors

## NO SUPPORT PROVIDED

- This is NOT supported by the original project
- No guarantees of any kind
- Use at your own risk
- You are responsible for any damage

## LEGAL DISCLAIMER

BY USING THIS FIRMWARE YOU ACKNOWLEDGE:
- You understand the risks described above
- You accept full responsibility for any damage
- You will not hold the authors liable
- You will comply with local RF regulations
- You have the technical skills to recover from failure

**DO NOT USE IN PRODUCTION**

---

Last updated: 2024-01-20
Branch: experimental/aggressive-performance
Status: UNTESTED - NO HARDWARE VALIDATION
