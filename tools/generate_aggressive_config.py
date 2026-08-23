#!/usr/bin/env python3
"""Regenerate the checked-in RM2100 3.4 experimental profile manifest."""

from __future__ import annotations

import json
from pathlib import Path


PROFILE = {
    "schema": 1,
    "mode": "aggressive",
    "status": "experimental",
    "base_profile": "rm2100-3.4-aggressive.config",
    "cpu_frequency": "1000",
    "features": {
        "hardware_nat": {
            "enabled": True,
            "runtime_mode": 4,
            "kernel_module": "CONFIG_RA_HW_NAT=m",
            "hnat_version": "HNAT_V2",
            "wifi_offload": True,
            "ipv6_offload": True,
        },
        "sfe": {"enabled": True, "default_mode": 1},
        "ethernet": {
            "qdma": True,
            "checksum_offload": True,
            "scatter_gather_tx": True,
            "tso": True,
            "tso_ipv6": True,
        },
        "scheduler": {"hz": 250, "preemption": "none"},
        "cpu_distribution": {
            "rps": True,
            "xps": True,
            "mt7621_irq_affinity": True,
        },
        "network_tuning": {
            "conntrack_default": 32768,
            "netdev_max_backlog": 2048,
            "somaxconn": 1024,
            "tcp_fast_open": False,
        },
        "compiler": {
            "userland_optimization": "-O2",
            "library_optimization": "-O2",
            "architecture": "mips32r2",
            "tune": "1004kc",
            "lto": False,
            "unsafe_math": False,
        },
    },
    "qualification": {
        "required": True,
        "minimum_soak_hours": 72,
        "must_measure": [
            "cpu_temperature",
            "wan_lan_throughput",
            "pppoe_stability",
            "vpn_compatibility",
            "wifi_client_compatibility",
            "conntrack_memory_pressure",
            "kernel_oops_and_panic_logs",
        ],
    },
    "disabled_until_qualified": [
        "compiler O3/LTO overrides",
        "unbounded conntrack increases",
        "regulatory transmit-power overrides",
        "bridge ingress bypass",
    ],
}


def main() -> None:
    output_path = Path(__file__).resolve().parents[1] / "config" / "aggressive-performance.json"
    output_path.write_text(json.dumps(PROFILE, indent=2) + "\n", encoding="utf-8")
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()
