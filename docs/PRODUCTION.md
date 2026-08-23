# Production gates

A successful GitHub Actions run creates a software-verified Firmware Bundle. Machine testing is intentionally not a release gate; the evidence below covers source provenance, configuration, compilation, image integrity and reproducibility, but does not claim device-specific thermal or radio qualification.

| Gate | Evidence | Required result |
| --- | --- | --- |
| Source Lock | `build-lock.json` and download logs | Exact Git commit and both SHA-256 checks pass |
| Firmware Profile | `rm2100-3.4.config` | RM2100, Linux 3.4, AU dual-band policy, selected CPU mode, approved options only |
| CPU baseline | `kernel-3.4.config` and `performance-profile.json` | Requested PLL mode, 4-way SMP, HZ=250, SFE, RPS and XPS all match |
| Runtime fast path | `runtime-policy.json` and prepared-source verification | SFE mode 1 is the clean-NVRAM default; bridge bypass is off; module state and failure fallback are verified |
| Aggressive tuning | `experimental-profile.json` and `runtime-policy.json` | HW NAT mode 4, bounded 32K conntrack, queue limits, target `-O2` and absence of O3/LTO/unsafe-math all match |
| Wireless source safety | `runtime-policy.json` and compiler warning gate | MT7615 SingleSKU spatial-stream inputs map only to compensation indexes 0-3; no array-bounds warning remains |
| Userland source safety | `runtime-policy.json` and compiler warning gate | HTTP ASCII length scope, HTTPS renegotiation policy and ebtables counter-file error propagation are verified |
| Image build safety | `runtime-policy.json` and compiler warning gate | BusyBox generator I/O is checked; LZMA searches all characters; ambiguous host-tool control flow and non-literal formats are absent |
| Compiler warnings | `build-warning-policy.json` | Every enforced high-risk warning category and the unknown-warning count are zero; each audited legacy category stays at or below its fixed limit |
| Public defaults | Repository config and prepared source | WebUI `admin/admin` and Wi-Fi `1234567890` are reproducibly installed and documented |
| Image integrity | `manifest.json` and `SHA256SUMS` | uImage header/data CRC, RM2100, 3.4, SHA-256 pass |
| Reproducibility | `reproducibility-policy.json` and second clean build | Two builds using the same locked source, profile and provisioning inputs are byte-identical; the sealed bundle hashes every payload (nine for default, ten for aggressive) |
| CI | GitHub Actions run URL | Tests and full firmware build pass |
| Security boundary | Source and profile review | WAN management closed; HTTPS is LAN-only; SSH, Telnet and unnecessary listeners are disabled |

## Release procedure

1. Manually run the default workflow for `bootloader`, `800`, `900` or `1000`, or run the aggressive workflow's fixed `1000` mode. Leave `release_version` empty for an automatic `YYYYMMDD.<run_number>` version, or enter a unique version in that format.
2. Wait for source validation, both clean builds, image verification and byte-for-byte reproducibility comparison to pass.
3. The dependent Release job reverifies the exact Artifact, attests the firmware image and creates an immutable GitHub Release. PR, push and scheduled runs never publish.
4. Download the released Firmware Bundle and verify `sha256sum --check SHA256SUMS` before deployment.
5. Publish the default address and credentials with the release, and instruct users to change both passwords immediately after first login.

`1000 MHz` is an optional overclock. Publishing it does not assert that every RM2100 unit has adequate voltage or thermal margin. `bootloader` remains the default release mode. Aggressive artifacts are always prereleases and require explicit risk acknowledgement; they must not be deployed until the complete hardware qualification worksheet passes.

## Rollback

Keep a known-working Firmware Bundle, bootloader backup and NVRAM migration notes. A rollout must stop on boot loops, loss of either radio, WAN failure, flash errors, unexpected listeners, thermal excursions or checksum mismatch. Recover through Breed and restore the known-working image before investigating. `HARDWARE-QUALIFICATION.md` is optional for the default profile and mandatory before deploying the aggressive profile. It does not block compilation, and an explicitly acknowledged aggressive prerelease may be published before device-specific evidence is complete.

## Residual risk

Linux 3.4 and OpenSSL 1.1.1 are end-of-life. The Source Lock makes builds auditable but does not make old code secure. The published defaults are intentionally public and therefore provide no protection until changed. Operators must isolate management access, change the WebUI and Wi-Fi passwords on first login, maintain a vulnerability inventory and backport applicable fixes.
