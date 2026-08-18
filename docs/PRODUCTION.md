# Production gates

A successful GitHub Actions run creates a Release Candidate, not a Production Release. Promotion requires one immutable Firmware Bundle to pass every gate below without rebuilding it.

| Gate | Evidence | Required result |
| --- | --- | --- |
| Source Lock | `build-lock.json` and download logs | Exact Git commit and both SHA-256 checks pass |
| Firmware Profile | `rm2100-3.4.config` | RM2100, Linux 3.4, SFE, HTTPS, approved options only |
| Provisioning | Build log and deployment record | No universal defaults; secrets absent from logs |
| Image integrity | `manifest.json` and `SHA256SUMS` | uImage header/data CRC, RM2100, 3.4, SHA-256 pass |
| CI | GitHub Actions run URL | Tests and full firmware build pass |
| Recovery | Hardware qualification | Breed recovery and rollback image tested |
| Stability | Hardware qualification | 72-hour soak, 50 cold boots, no crash or persistent corruption |
| Routing | Hardware qualification | DHCP, static WAN, PPPoE, NAT, IPv6 and DNS pass |
| Performance | Hardware qualification | Wired NAT >= 900 Mbit/s with SFE; no >5% regression from baseline |
| Wireless | Hardware qualification | Both radios pass association, reconnect and 24-hour traffic soak |
| Resource limits | Hardware qualification | No sustained memory growth; temperature stays within device limit |
| Security | Review record | WAN management closed; unnecessary listeners absent; known risks accepted |

## Release procedure

1. Build with `publish=false` and retain the Actions run URL.
2. Verify `sha256sum --check SHA256SUMS` on a separate Linux host.
3. Flash the exact `.trx` from that Firmware Bundle onto a qualification device.
4. Complete `docs/HARDWARE-QUALIFICATION.md` without rebuilding.
5. Record the manifest SHA-256, device identity, bootloader backup and test equipment.
6. Promote only the tested bundle. A new build, even from the same source, requires a new qualification record.

## Rollback

Keep the last qualified Firmware Bundle, bootloader backup and NVRAM migration notes. A rollout must stop on boot loops, loss of either radio, WAN failure, flash errors, unexpected listeners, thermal excursions or checksum mismatch. Recover through Breed and restore the last qualified image before investigating.

## Residual risk

Linux 3.4 and OpenSSL 1.1.1 are end-of-life. The Source Lock makes builds auditable but does not make old code secure. Production operators must maintain a vulnerability inventory, backport applicable fixes, isolate management access, and repeat qualification after every security patch.
