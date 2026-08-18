# RM2100 hardware qualification record

Copy this file for each candidate. Do not edit the template to claim generic qualification.

## Identity

- Firmware filename:
- Firmware SHA-256:
- Manifest SHA-256:
- GitHub Actions run:
- Builder commit:
- Upstream commit:
- CPU mode (`900` or `bootloader`):
- Observed CPU clock after boot:
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
- [ ] 2.4 GHz and 5 GHz association, WPA2 and reconnect pass
- [ ] Both radios report AU and expose only AU-permitted channels
- [ ] 5 GHz DFS channel detection, CAC and radar fallback behave correctly
- [ ] Reset button, LEDs and all Ethernet ports pass

## Stability

- [ ] 50 cold boot cycles complete without a boot loop
- [ ] 72-hour mixed wired/wireless soak completes without crash
- [ ] Selected CPU mode remains stable under simultaneous NAT and dual-band load
- [ ] Repeated WAN reconnect and radio restart do not leak resources
- [ ] NVRAM settings survive power cycles and factory reset clears them

Record free memory, load, temperature and error counters at 0, 24, 48 and 72 hours.

## Performance

Use the same client, server, cables, channel, distance and iperf3 parameters as the previous qualified baseline.

| Test | Baseline | Candidate | Pass |
| --- | ---: | ---: | :---: |
| Wired LAN-WAN TCP, SFE enabled | | | |
| Wired LAN-WAN UDP loss | | | |
| 5 GHz TCP at 2 m | | | |
| 2.4 GHz TCP at 2 m | | | |
| CPU load during wired test | | | |
| Observed CPU clock | | | |
| Peak temperature during soak | | | |

Pass criteria: wired TCP is at least 900 Mbit/s, packet loss is not worse than baseline, and no measured result regresses by more than 5% without an accepted explanation.

## Decision

- [ ] Production Release approved
- [ ] Rejected

Reason and known limitations:
