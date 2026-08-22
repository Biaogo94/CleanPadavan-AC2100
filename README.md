# CleanPadavan AC2100: Linux 3.4 aggressive profile

This branch builds only the Redmi AC2100 (RM2100) Padavan Linux 3.4 firmware.
It is an experimental performance profile and is intentionally separate from the
production branch. It has not received hardware qualification.

## What is actually enabled

- MT7621 CPU PLL forced to 1000 MHz.
- The existing MT7621 HW NAT v2 kernel module is built and the runtime default is
  changed from `hw_nat_mode=2` (disabled for MT7615) to `hw_nat_mode=4` (IPv4,
  Wi-Fi and UDP offload; IPv6 follows the upstream capability check).
- SFE mode 1, QDMA, checksum offload, scatter-gather TX, TSO/TSOv6, RPS and XPS.
- The same source-lock, warning policy, reproducible-build and image validation
  gates as the production 3.4 pipeline.

The bundle contains `experimental-profile.json` and a manifest entry that record
the experimental mode and the required hardware qualification status. Claims of
global `-O3`, LTO, bridge bypass, regulatory overrides, or unbounded conntrack
increases are deliberately disabled until measured and reviewed.

## Risk

This profile may overheat, become unstable, or lose compatibility with PPPoE,
VPNs, Wi-Fi clients, or unusual MT7615 traffic. Keep a serial/Breed recovery path,
back up the current firmware, and monitor temperature. The workflow may publish a
clearly marked GitHub prerelease after an explicit risk acknowledgement, but do
not deploy it until the checklist in
[docs/HARDWARE-QUALIFICATION.md](docs/HARDWARE-QUALIFICATION.md) has been completed
on the target hardware.

## GitHub Actions

Run **Build RM2100 Padavan 3.4 (AGGRESSIVE - EXPERIMENTAL)** from the Actions page.
Manual dispatch always uses the aggressive profile and 1000 MHz. Set `publish` to
true and type `I_UNDERSTAND` in `confirm_risk` only when you want the verified
artifact promoted to an explicitly experimental Release. Pushes and pull requests
build and upload an artifact but never publish a Release.

## Local build

On Ubuntu 22.04 with the dependencies listed in the workflow:

```sh
PROFILE_FILE=config/rm2100-3.4-aggressive.config \
EXPERIMENTAL_PROFILE_FILE=config/aggressive-performance.json \
CPU_FREQUENCY=1000 \
bash scripts/build-firmware.sh
```

The output is written to `dist/`. The public first-boot credentials are
`admin` / `admin` for the WebUI and `1234567890` for both Wi-Fi networks. Change
them immediately after first login.

## Scope

The 4.4 kernel is intentionally out of scope. The source, toolchain, profile and
workflow are locked to Linux 3.4 and the RM2100 board.
