# Production gates

A successful GitHub Actions run creates a Release Candidate, not a Production Release. Promotion requires one immutable Firmware Bundle to pass every gate below without rebuilding it.

| Gate | Evidence | Required result |
| --- | --- | --- |
| Source Lock | `build-lock.json` and download logs | Exact Git commit and both SHA-256 checks pass |
| Firmware Profile | `rm2100-3.4.config` | RM2100, Linux 3.4, AU dual-band policy, selected CPU mode, approved options only |
| CPU baseline | `kernel-3.4.config` and `performance-profile.json` | Requested PLL mode, 4-way SMP, HZ=250, SFE, RPS and XPS all match |
| Runtime fast path | `runtime-policy.json` and prepared-source verification | SFE mode 1 is the clean-NVRAM default; bridge bypass is off; module state and failure fallback are verified |
| Wireless source safety | `runtime-policy.json` and compiler warning gate | MT7615 SingleSKU spatial-stream inputs map only to compensation indexes 0-3; no array-bounds warning remains |
| Userland source safety | `runtime-policy.json` and compiler warning gate | HTTP ASCII length scope, HTTPS renegotiation policy and ebtables counter-file error propagation are verified |
| Image build safety | `runtime-policy.json` and compiler warning gate | BusyBox generator I/O is checked; LZMA searches all characters; ambiguous host-tool control flow and non-literal formats are absent |
| Compiler warnings | `build-warning-policy.json` | Every enforced high-risk warning category and the unknown-warning count are zero; each audited legacy category stays at or below its fixed limit |
| Provisioning | Build log and deployment record | No universal defaults; secrets absent from logs |
| Image integrity | `manifest.json` and `SHA256SUMS` | uImage header/data CRC, RM2100, 3.4, SHA-256 pass |
| CI | GitHub Actions run URL | Tests and full firmware build pass |
| Recovery | Hardware qualification | Breed recovery and rollback image tested |
| Stability | Hardware qualification | 72-hour soak, 50 cold boots, no crash or persistent corruption |
| Routing | Hardware qualification | DHCP, static WAN, PPPoE, NAT, IPv6 and DNS pass |
| Performance | Hardware qualification | Wired NAT >= 900 Mbit/s with SFE mode 1; CPU cost and throughput show no >5% unexplained regression |
| Wireless | Hardware qualification | Both AU-configured radios expose the expected channels and pass association, reconnect and 24-hour traffic soak |
| Resource limits | Hardware qualification | No sustained memory growth; temperature stays within device limit |
| Security | Review record | WAN management closed; unnecessary listeners absent; known risks accepted |

## Release procedure

1. Build with `publish=false` and retain the Actions run URL.
2. Verify `sha256sum --check SHA256SUMS` on a separate Linux host.
3. Flash the exact `.trx` from that Firmware Bundle onto a qualification device.
4. Complete `docs/HARDWARE-QUALIFICATION.md` without rebuilding.
5. Record the manifest SHA-256, device identity, bootloader backup and test equipment.
6. Confirm `fast_classifier` is loaded, `skip_to_bridge_ingress` is `0`, and no SFE load/unload failure is present in the system log.
7. Promote only the tested bundle. A different CPU mode or any new build requires a new qualification record.

## Rollback

Keep the last qualified Firmware Bundle, bootloader backup and NVRAM migration notes. A rollout must stop on boot loops, loss of either radio, WAN failure, flash errors, unexpected listeners, thermal excursions or checksum mismatch. Recover through Breed and restore the last qualified image before investigating.

## Residual risk

Linux 3.4 and OpenSSL 1.1.1 are end-of-life. The Source Lock makes builds auditable but does not make old code secure. Production operators must maintain a vulnerability inventory, backport applicable fixes, isolate management access, and repeat qualification after every security patch.
