# Performance and stability design

This project optimizes the locked RM2100 Linux 3.4 source without treating unmeasured tuning as an improvement. Every source change must preserve the bootloader-clock path, compile in both CPU modes, and have a hardware acceptance criterion.

## CPU and scheduler

- The safe default is the clock selected by the device bootloader. `900` is an explicit build option that enables upstream `CONFIG_RALINK_MT7621_PLL900`.
- The final kernel must have four logical CPUs, SMP, `HZ=250` and non-preemptible kernel scheduling. The build rejects any drift.
- CPU sleep remains disabled. The 900 MHz image cannot be promoted from build evidence alone; it needs cold-boot, thermal and 72-hour mixed-load qualification.

## Packet forwarding

The RM2100 kernel already enables NAPI, GRO, BQL, QDMA transmit, checksum offload, scatter-gather, TSO/TSOv6, SFE, RPS and XPS. The upstream SMP code assigns FE and both PCIe Wi-Fi interrupts across the four logical CPUs and configures per-interface RPS/XPS masks.

The clean-NVRAM runtime default is SFE mode 1. It accelerates established TCP/UDP flows while leaving `skip_to_bridge_ingress=0`, so the experimental bridge shortcut described by the upstream SFE source remains disabled. The source patch also rechecks `fast_classifier` after every load or unload. A failed load restores `nf_conntrack_tcp_be_liberal=1` and `nf_conntrack_tcp_no_window_check=1` instead of leaving conntrack in a stricter half-configured state.

Hardware NAT remains disabled by default for the MT7615 path, matching upstream policy. QDMA receive, hardware-NAT Wi-Fi offload and a lower SFE offload threshold are not enabled without packet-loss, reconnect and long-soak evidence. They change driver concurrency or allocate acceleration state more aggressively and are not justified by a compile-only result.

## Wireless and memory

- AU selects the regulatory path; it does not bypass EEPROM/SingleSKU calibration or regulatory power limits.
- The 5 GHz driver retains 80 MHz, aggregation, beamforming, LDPC and the board's 4x4 stream layout. MU-MIMO remains off because it requires client-mix and soak evidence.
- The 2.4 GHz driver retains 20/40 MHz, WMM, aggregation and the board's 2x2 layout.
- The 128 MiB memory policy and 16,384-connection default are unchanged. Raising conntrack limits or adding swap would reduce stability margin under sustained traffic.

## Image builder correctness

The locked upstream `mkimage` host tool originally parsed dotted kernel and filesystem versions with `%d` directly into `uint8_t` fields. That makes `sscanf` write an `int` through a one-byte pointer and can overwrite adjacent uImage tail fields. Source preparation changes the conversions to `%hhu` and checks their return counts. The resulting image is still independently checked for header CRC, data CRC, Linux 3.4, filesystem 3.9 and RM2100 identity.

## Measurement contract

Qualification compares the same immutable bundle and test setup with SFE disabled and SFE mode 1. Record bidirectional TCP throughput, UDP loss, CPU load, free memory, temperature, SFE exceptions and interface errors. Promotion requires at least 900 Mbit/s wired TCP with SFE mode 1, no unexplained regression above 5%, no persistent memory growth, and no crash or packet-loss excursion during the 72-hour soak.
