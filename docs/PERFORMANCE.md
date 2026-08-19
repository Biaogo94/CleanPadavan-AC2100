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

The MT7615 5.0.5.1 SingleSKU transmit-power compensation path originally initialized its spatial-stream array index to zero and then subtracted one when spatial expansion was active. Source preparation restores the intended 1-4 stream to 0-3 index mapping and maps an invalid stream count to the conservative single-stream entry. Legal inputs keep their original calibration result, while malformed ATE input can no longer read before the compensation array.

## Image builder correctness

The locked upstream `mkimage` host tool originally parsed dotted kernel and filesystem versions with `%d` directly into `uint8_t` fields. That makes `sscanf` write an `int` through a one-byte pointer and can overwrite adjacent uImage tail fields. Source preparation changes the conversions to `%hhu` and checks their return counts. The resulting image is still independently checked for header CRC, data CRC, Linux 3.4, filesystem 3.9 and RM2100 identity.

BusyBox 1.24 host generators also ignored reads, pipe creation, writes and output flush failures while producing Kconfig, applet and compressed-usage headers. Those results are now checked, so an incomplete generated file stops the build. The compiler gate rejects any remaining `warn_unused_result` diagnostic instead of treating generator I/O failures as legacy noise.

The LZMA 4.65 host library used by the image build had a mis-scoped `FindOneOf()` loop: `return -1` executed after the first character instead of after the full search. Source preparation restores the complete search, makes reference-count and property-parser control flow explicit, scopes the optional threaded match-finder value to threaded builds, and replaces non-literal diagnostic formats. These host changes do not alter compression parameters; they remove ambiguous behavior in the tool that creates the root filesystem.

Reproducible output is enforced as a build property, not inferred from a fixed uImage header. Linux 3.4 receives a locked build timestamp, user, host and version; BusyBox and every SquashFS inode use the Source Lock epoch in UTC. CI then removes the exact build directory and performs a second clean build at the same canonical absolute path with the same provisioning inputs. This prevents compiler or generator path leakage and rejects any byte difference before sealing `reproducibility-policy.json` into the checksummed Firmware Bundle. Public runs still use fresh random credentials between separate runs, so reproducibility is proved within each run using the same protected inputs.

## Compiled userland correctness

The default root filesystem includes the router startup process, HTTP/HTTPS management, ebtables, 802.1X, PPTP relay, LAN authentication, UDP multicast proxy, wireless interface renaming, UPnP event handling and xl2tpd even when optional add-on features are disabled. Source preparation therefore fixes the high-risk warnings in those compiled paths instead of dismissing them as third-party noise: missing declarations are added, `isdigit` receives an unsigned byte, empty strings are checked by content, the PPTP interface expression is bounded, and intentional state-machine fallthrough and conditional close scopes are explicit. HTTP hexadecimal input now applies its minimum-length check to every accepted ASCII branch. Modern OpenSSL disables renegotiation at `SSL_CTX` creation, and ebtables propagates atomic counter-file read, write and close failures instead of reporting success.

The complete build is captured with `LC_ALL=C` and checked after linking. `build-warning-policy.json` proves that the enforced high-risk categories and unknown warning count are zero. The gate rejects implicit function declarations, format argument type mismatches, non-literal formats, string-literal address comparisons, truncation, accidental fallthrough, ambiguous indentation or parentheses, array bounds, overflow, uninitialized or unused assigned values, ignored I/O results, discarded qualifiers, macro redefinitions, use-after-free, null dereferences, incompatible pointer conversions and missing returns. The remaining diagnostics must match one of seven audited legacy categories, each with a fail-closed upper limit. Obsolete build-system diagnostics, intentional compile-time assertions and compiler inlining decisions therefore remain visible without allowing a new warning type or an unexplained count increase.

## Measurement contract

Qualification compares the same immutable bundle and test setup with SFE disabled and SFE mode 1. Record bidirectional TCP throughput, UDP loss, CPU load, free memory, temperature, SFE exceptions and interface errors. Promotion requires at least 900 Mbit/s wired TCP with SFE mode 1, no unexplained regression above 5%, no persistent memory growth, and no crash or packet-loss excursion during the 72-hour soak.
