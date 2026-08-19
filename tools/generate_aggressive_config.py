#!/usr/bin/env python3
"""
Aggressive performance optimization patches for RM2100 firmware.
EXPERIMENTAL - UNTESTED - HIGH RISK
"""

from pathlib import Path
import json


AGGRESSIVE_KERNEL_OPTIONS = {
    # Force 1000 MHz
    "CONFIG_RALINK_MT7621_PLL1000": "y",
    "CONFIG_RALINK_MT7621_PLL900": "n",
    "CONFIG_RALINK_MT7621_PLL800": "n",
    
    # Hardware NAT (HIGH RISK)
    "CONFIG_RA_HW_NAT": "y",
    "CONFIG_RA_HW_NAT_WIFI": "y",
    "CONFIG_RA_HW_NAT_NIC_USB": "y",
    "CONFIG_RA_HW_NAT_IPV6": "y",
    
    # Aggressive packet processing
    "CONFIG_RAETH_QDMA": "y",
    "CONFIG_RAETH_TSO": "y",
    "CONFIG_RAETH_TSOV6": "y",
    "CONFIG_RAETH_SG_DMA_TX": "y",
    "CONFIG_RAETH_CHECKSUM_OFFLOAD": "y",
    
    # SFE with all features
    "CONFIG_SHORTCUT_FE": "y",
    "CONFIG_NF_CONNTRACK_EVENTS": "y",
    "CONFIG_NF_CONNTRACK_CHAIN_EVENTS": "y",
    
    # RPS/XPS
    "CONFIG_RPS": "y",
    "CONFIG_XPS": "y",
    
    # Reduce context switch overhead
    "CONFIG_HZ_250": "y",
    "CONFIG_HZ_1000": "n",
    "CONFIG_HZ": "250",
    
    # Aggressive preemption
    "CONFIG_PREEMPT_NONE": "y",
    "CONFIG_PREEMPT_VOLUNTARY": "n",
    "CONFIG_PREEMPT": "n",
    
    # Disable debugging for performance
    "CONFIG_DEBUG_KERNEL": "n",
    "CONFIG_DEBUG_INFO": "n",
    "CONFIG_KALLSYMS": "n",
    "CONFIG_PRINTK": "y",
    
    # Optimize memory allocator
    "CONFIG_SLUB": "y",
    "CONFIG_SLAB": "n",
    "CONFIG_SLOB": "n",
    
    # Increase conntrack limits
    "CONFIG_NF_CONNTRACK_MAX": "65536",
    
    # QoS for traffic shaping
    "CONFIG_NET_SCHED": "y",
    "CONFIG_NET_SCH_HTB": "y",
    "CONFIG_NET_SCH_SFQ": "y",
    "CONFIG_NET_SCH_FQ_CODEL": "y",
    "CONFIG_IFB": "y",
    "CONFIG_IMQ": "y",
}


AGGRESSIVE_SYSCTL = {
    "net.netfilter.nf_conntrack_max": "65536",
    "net.netfilter.nf_conntrack_buckets": "16384",
    "net.ipv4.tcp_fastopen": "3",
    "net.ipv4.tcp_fin_timeout": "15",
    "net.core.netdev_max_backlog": "5000",
    "net.core.somaxconn": "4096",
    "vm.swappiness": "0",
}


def generate_aggressive_config():
    config = {
        "mode": "aggressive",
        "warnings": [
            "UNTESTED - May damage hardware",
            "CPU overclocked to 1000 MHz",
            "Hardware NAT enabled",
        ],
        "kernel_options": AGGRESSIVE_KERNEL_OPTIONS,
        "sysctl": AGGRESSIVE_SYSCTL,
    }
    output_path = Path(__file__).parent.parent / "config" / "aggressive-performance.json"
    output_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    generate_aggressive_config()
