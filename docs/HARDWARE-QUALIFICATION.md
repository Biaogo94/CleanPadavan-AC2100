# RM2100 hardware qualification record

This worksheet is required before deploying the aggressive profile. It is not an
automated build gate: the workflow can publish a clearly marked prerelease only
after an explicit risk acknowledgement, but that prerelease must not be deployed
until this device-specific evidence is complete. Do not edit the template to claim
generic qualification.

## Identity

- Firmware filename:
- Firmware SHA-256:
- Manifest SHA-256:
- GitHub Actions run:
- Builder commit:
- Upstream commit:
- CPU mode (`bootloader`, `800`, `900` or `1000`):
- Observed CPU clock after boot:
- SFE mode / `fast_classifier` loaded:
- Wi-Fi country code shown by both radios:
- Router serial / MAC suffix:
- Bootloader and recovery version:
- Tester and date:

## Recovery and upgrade

- [ ] Bootloader and current firmware backup verified
- [ ] Clean flash succeeds
- [ ] Factory reset succeeds
- [ ] Rollback to the last qualified image succeeds
- [ ] Power interruption during normal boot does not corrupt persistent storage

## Functional

- [ ] HTTPS management is unavailable from WAN and guest networks
- [ ] Default SSH, Telnet and ttyd listeners are absent
- [ ] DHCP WAN, static WAN and PPPoE pass
- [ ] IPv4 NAT, IPv6 routing, DNS and NTP pass
- [ ] SFE mode 1 loads `fast_classifier`; bridge ingress bypass reports `0`
- [ ] Aggressive profile reports `hw_nat_mode=4` and `/sys/module/hw_nat` is loaded
- [ ] Hardware NAT IPv4 TCP/UDP flow entries are created and expire correctly
- [ ] Hardware NAT Wi-Fi offload passes bidirectional traffic without packet loss
- [ ] PPPoE, VPN, IPv6 and WAN reconnect tests pass with Hardware NAT enabled
- [ ] Twenty SFE disable/enable cycles under active traffic complete without stale state or a load/unload failure log
- [ ] 2.4 GHz and 5 GHz association, WPA2 and reconnect pass
- [ ] Both radios report AU; 2.4 GHz exposes 1-13 and 5 GHz exposes 36-48/149-165
- [ ] Reset button, LEDs and all Ethernet ports pass

## Stability

- [ ] 50 cold boot cycles complete without a boot loop
- [ ] 72-hour mixed wired/wireless soak completes without crash
- [ ] Selected CPU mode remains stable under simultaneous NAT and dual-band load
- [ ] Repeated WAN reconnect and radio restart do not leak resources
- [ ] NVRAM settings survive power cycles and factory reset clears them

Record free memory, load, temperature and error counters at 0, 24, 48 and 72 hours.

### Evidence collector

Run `scripts/collect-hardware-evidence.sh` on the qualification router from a local console or a temporary LAN-only management session. The script is POSIX/BusyBox compatible and uses an explicit safe NVRAM allowlist; it never runs `nvram show` or reads password/PSK keys. If SSH is temporarily enabled to transfer or run the script, disable it afterwards and separately verify that the clean production configuration has no SSH listener.

One-time snapshot:

```sh
chmod 700 /tmp/collect-hardware-evidence.sh
/tmp/collect-hardware-evidence.sh snapshot /tmp/rm2100-candidate-snapshot
(cd /tmp/rm2100-candidate-snapshot && sha256sum -c SHA256SUMS)
```

The default 72-hour schedule records 73 hourly samples, including both endpoints:

```sh
/tmp/collect-hardware-evidence.sh soak /tmp/rm2100-candidate-soak 3600 73
(cd /tmp/rm2100-candidate-soak && sha256sum -c SHA256SUMS)
tar -C /tmp -czf /tmp/rm2100-candidate-soak.tar.gz rm2100-candidate-soak
```

Archive the evidence next to this completed record. Treat the archive as confidential qualification data because interface, route and radio diagnostics can contain local IP and MAC addresses; do not attach it to a public issue or release. `samples.tsv` tracks uptime, one-minute load, free/available memory, the first readable temperature sensor, and aggregate interface error/drop counters. The snapshot also records safe identity/configuration keys, non-command-line process status, loaded modules, SFE bridge-bypass state and exception counters, listeners, radio statistics and filtered fault events. Fault-event lines containing credential-related keywords are discarded. The collector deliberately does not read the SFE IPv4/IPv6 debug character devices because they expose connection tuples. A missing temperature sensor is reported as `NA` and requires an external measurement; it is not a pass.

## Performance

Use the same client, server, cables, channel, distance and iperf3 parameters as the previous qualified baseline.

| Test | Baseline | Candidate | Pass |
| --- | ---: | ---: | :---: |
| Wired LAN-WAN TCP, SFE disabled reference | | | |
| Wired LAN-WAN TCP, SFE mode 1 | | | |
| Wired LAN-WAN UDP loss | | | |
| 5 GHz TCP at 2 m | | | |
| 2.4 GHz TCP at 2 m | | | |
| CPU load, SFE disabled / mode 1 | | | |
| Observed CPU clock | | | |
| Peak temperature during soak | | | |

Suggested pass criteria: SFE mode 1 wired TCP is at least 900 Mbit/s, packet loss is not worse than baseline, and no measured result regresses by more than 5% without an accepted explanation. Every forced-frequency image should record its temperature margin against the bootloader-clock image; this is especially important for the optional 1000 MHz overclock.

## Decision

- [ ] Production Release approved
- [ ] Rejected

Reason and known limitations:
