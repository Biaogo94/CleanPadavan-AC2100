#!/usr/bin/env python3
"""Build preparation and verification interface for RM2100 firmware."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path


ALLOWED_ENABLED_OPTIONS = frozenset(
    {
        "CONFIG_FIRMWARE_CPU_900MHZ",
        "CONFIG_FIRMWARE_ENABLE_IPV6",
        "CONFIG_FIRMWARE_INCLUDE_HTTPS",
        "CONFIG_FIRMWARE_INCLUDE_IPSET",
        "CONFIG_FIRMWARE_INCLUDE_LANG_CN",
        "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC",
        "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE",
        "CONFIG_FIRMWARE_INCLUDE_SFE",
    }
)
REQUIRED_PROFILE_VALUES = {
    "CONFIG_FIRMWARE_INCLUDE_SFE": "y",
    "CONFIG_VENDOR": "Ralink",
    "CONFIG_PRODUCT": "MT7621",
    "CONFIG_FIRMWARE_PRODUCT_ID": '"RM2100"',
    "CONFIG_LINUXDIR": "linux-3.4.x",
    "CONFIG_FIRMWARE_KERNEL_CONFIG": '"kernel-3.4.x-5.0.config"',
    "CONFIG_FIRMWARE_WIFI2_DRIVER": "4.1",
    "CONFIG_FIRMWARE_WIFI5_DRIVER": "5.0.5.1",
    "CONFIG_FIRMWARE_WLAN_COUNTRY_CODE": '"AU"',
    "CONFIG_FIRMWARE_ENABLE_IPV6": "y",
    "CONFIG_FIRMWARE_INCLUDE_IPSET": "y",
    "CONFIG_FIRMWARE_INCLUDE_LANG_CN": "y",
    "CONFIG_FIRMWARE_INCLUDE_HTTPS": "y",
    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC": "y",
    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE": "y",
}
CPU_PROFILE_OPTION = "CONFIG_FIRMWARE_CPU_900MHZ"
CPU_FREQUENCIES = {"bootloader": "n", "900": "y"}
KERNEL_BASELINE = {
    "CONFIG_RALINK_MT7621": "y",
    "CONFIG_SMP": "y",
    "CONFIG_NR_CPUS": "4",
    "CONFIG_HZ": "250",
    "CONFIG_PREEMPT_NONE": "y",
    "CONFIG_SHORTCUT_FE": "y",
    "CONFIG_NF_CONNTRACK_EVENTS": "y",
    "CONFIG_RPS": "y",
    "CONFIG_XPS": "y",
}
IMAGE_HEADER = struct.Struct(">7I4B28sI")
IMAGE_MAGIC = 0x27051956
MIN_IMAGE_SIZE = 4 * 1024 * 1024
MAX_IMAGE_SIZE = 16 * 1024 * 1024
SFE_DEFAULT_DISABLED = '\t{ "sfe_enable", "0" },'
SFE_DEFAULT_ENABLED = '\t{ "sfe_enable", "1" },'
SFE_RUNTIME_ORIGINAL = """\
\tif (sfe_loaded && !sfe_enable) {
\t\tmodule_smart_unload("fast_classifier", 1);
\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tsfe_loaded = 0;
\t}
\tif (sfe_enable && !sfe_loaded) {
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tmodule_smart_load("fast_classifier", NULL);
\t\tsfe_loaded = 1;
\t}
\tif (sfe_loaded) {
\t\tif (sfe_enable == 1)
\t\t\tdoSystem("echo 0 > /sys/fast_classifier/skip_to_bridge_ingress");
\t\telse if (sfe_enable == 2)
\t\t\tdoSystem("echo 1 > /sys/fast_classifier/skip_to_bridge_ingress");
\t}
"""
SFE_RUNTIME_HARDENED = """\
\tif (sfe_loaded && !sfe_enable) {
\t\tmodule_smart_unload("fast_classifier", 1);
\t\tsfe_loaded = is_module_loaded("fast_classifier");
\t\tif (!sfe_loaded) {
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\t} else {
\t\t\tlogmessage(LOGNAME, "%s", "SFE module unload failed");
\t\t}
\t}
\tif (sfe_enable && !sfe_loaded) {
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\tmodule_smart_load("fast_classifier", NULL);
\t\tsfe_loaded = is_module_loaded("fast_classifier");
\t\tif (!sfe_loaded) {
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");
\t\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");
\t\t\tlogmessage(LOGNAME, "%s", "SFE module load failed");
\t\t}
\t}
\tif (sfe_loaded) {
\t\tif (sfe_enable == 1)
\t\t\tdoSystem("echo 0 > /sys/fast_classifier/skip_to_bridge_ingress");
\t\telse if (sfe_enable == 2)
\t\t\tdoSystem("echo 1 > /sys/fast_classifier/skip_to_bridge_ingress");
\t}
"""


class FirmwareError(ValueError):
    """An input cannot produce a supported firmware bundle."""


def parse_profile(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise FirmwareError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        if key in values:
            raise FirmwareError(f"{path}:{line_number}: duplicate key {key}")
        values[key] = value
    return values


def validate_profile(path: Path) -> dict[str, str]:
    values = parse_profile(path)
    if values.get("CONFIG_LINUXDIR") != "linux-3.4.x":
        raise FirmwareError("CONFIG_LINUXDIR must be linux-3.4.x")
    if values.get("CONFIG_FIRMWARE_PRODUCT_ID") != '"RM2100"':
        raise FirmwareError('CONFIG_FIRMWARE_PRODUCT_ID must be "RM2100"')
    unsupported = sorted(
        key for key, value in values.items() if value == "y" and key not in ALLOWED_ENABLED_OPTIONS
    )
    if unsupported:
        raise FirmwareError(f"unsupported enabled option: {', '.join(unsupported)}")
    for key, expected in REQUIRED_PROFILE_VALUES.items():
        if values.get(key) != expected:
            raise FirmwareError(f"{key} must be {expected}")
    if values.get(CPU_PROFILE_OPTION) not in CPU_FREQUENCIES.values():
        raise FirmwareError(f"{CPU_PROFILE_OPTION} must be n or y")
    return values


def cpu_frequency_from_profile(values: dict[str, str]) -> str:
    return "900" if values[CPU_PROFILE_OPTION] == "y" else "bootloader"


def configure_profile(source: Path, output: Path, cpu_frequency: str) -> None:
    validate_profile(source)
    if cpu_frequency not in CPU_FREQUENCIES:
        raise FirmwareError("CPU frequency must be bootloader or 900")
    content = source.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(CPU_PROFILE_OPTION)}=.*$", re.MULTILINE)
    content, count = pattern.subn(
        f"{CPU_PROFILE_OPTION}={CPU_FREQUENCIES[cpu_frequency]}", content
    )
    if count != 1:
        raise FirmwareError(f"expected exactly one {CPU_PROFILE_OPTION}, found {count}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    validate_profile(output)


def load_lock(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        source = document["source"]
        archives = document["archives"]
        if document["schema"] != 1 or not isinstance(source, dict) or not isinstance(archives, dict):
            raise KeyError("schema")
        if source["url"] != "https://github.com/hanwckf/rt-n56u.git":
            raise FirmwareError("Source Lock must use the hanwckf 3.4 repository")
        if not re.fullmatch(r"[0-9a-f]{40}", str(source["commit"])):
            raise FirmwareError("Source Lock commit must be a full lowercase Git SHA")
        if not isinstance(source["source_date_epoch"], int) or source["source_date_epoch"] <= 0:
            raise FirmwareError("Source Lock source_date_epoch must be a positive integer")
        for archive_name in ("toolchain", "openssl"):
            archive = archives[archive_name]
            if not isinstance(archive, dict) or not str(archive["url"]).startswith("https://"):
                raise FirmwareError(f"Source Lock {archive_name} URL must use HTTPS")
            if not re.fullmatch(r"[0-9a-f]{64}", str(archive["sha256"])):
                raise FirmwareError(f"Source Lock {archive_name} SHA-256 is invalid")
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise FirmwareError(f"invalid Source Lock: {error}") from error
    if "4.4" in json.dumps(document, sort_keys=True):
        raise FirmwareError("Source Lock must not contain a 4.4 source")
    return document


def lock_value(path: Path, dotted_key: str) -> object:
    value: object = load_lock(path)
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise FirmwareError(f"Source Lock has no value for {dotted_key}")
        value = value[part]
    if isinstance(value, (dict, list)):
        raise FirmwareError(f"Source Lock value {dotted_key} is not scalar")
    return value


def read_secret(path: Path, label: str, minimum: int, maximum: int, forbidden: set[str]) -> str:
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if value in forbidden:
        raise FirmwareError(f"{label} uses a forbidden universal default")
    if not minimum <= len(value) <= maximum:
        raise FirmwareError(f"{label} must contain {minimum}-{maximum} characters")
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise FirmwareError(f"{label} must contain printable ASCII without spaces")
    return value


def validate_credentials(admin_path: Path, wifi_path: Path) -> tuple[str, str]:
    admin_password = read_secret(
        admin_path, "administrator password", 16, 64, {"admin", "password"}
    )
    wifi_password = read_secret(
        wifi_path, "Wi-Fi password", 16, 63, {"1234567890", "password"}
    )
    if admin_password == wifi_password:
        raise FirmwareError("administrator password and Wi-Fi password must differ")
    return admin_password, wifi_password


def replace_c_define(content: str, name: str, value: str) -> str:
    pattern = re.compile(rf"^#define\s+{re.escape(name)}\s+.*$", re.MULTILINE)
    replacement = f"#define {name}\t{json.dumps(value)}"
    updated, count = pattern.subn(replacement, content)
    if count != 1:
        raise FirmwareError(f"expected exactly one C definition for {name}, found {count}")
    return updated


def replace_exact_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    if count != 1:
        raise FirmwareError(f"expected exactly one {label}, found {count}")
    return content.replace(old, new, 1)


def prepare_source(
    source: Path, profile: Path, admin_password_file: Path, wifi_password_file: Path
) -> None:
    profile_values = validate_profile(profile)
    admin_password, wifi_password = validate_credentials(
        admin_password_file, wifi_password_file
    )

    template = source / "trunk" / "configs" / "templates" / "RM2100.config"
    defaults = source / "trunk" / "user" / "shared" / "defaults.h"
    if not template.is_file() or not defaults.is_file():
        raise FirmwareError(f"source tree is not a supported RM2100 checkout: {source}")

    shutil.copyfile(profile, template)
    defaults_content = defaults.read_text(encoding="utf-8")
    defaults_content = replace_c_define(
        defaults_content, "DEF_ROOT_PASSWORD", admin_password
    )
    country_code = profile_values["CONFIG_FIRMWARE_WLAN_COUNTRY_CODE"].strip('"')
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_2G_CC", country_code)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_5G_CC", country_code)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_2G_PSK", wifi_password)
    defaults_content = replace_c_define(defaults_content, "DEF_WLAN_5G_PSK", wifi_password)
    defaults.write_text(defaults_content, encoding="utf-8", newline="\n")

    runtime_defaults = source / "trunk" / "user" / "shared" / "defaults.c"
    if runtime_defaults.is_file():
        runtime_content = runtime_defaults.read_text(encoding="utf-8")
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "http_access", "0" }',
            '{ "http_access", "2" }',
            "http_access default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "http_proto", "0" }',
            '{ "http_proto", "1" }',
            "http_proto default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            '{ "sshd_enable", "1" }',
            '{ "sshd_enable", "0" }',
            "sshd_enable default",
        )
        runtime_content = replace_exact_once(
            runtime_content,
            SFE_DEFAULT_DISABLED,
            SFE_DEFAULT_ENABLED,
            "SFE runtime default",
        )
        runtime_defaults.write_text(runtime_content, encoding="utf-8", newline="\n")

    runtime_network = source / "trunk" / "user" / "rc" / "net.c"
    if runtime_network.is_file():
        network_content = runtime_network.read_text(encoding="utf-8")
        network_content = replace_exact_once(
            network_content,
            SFE_RUNTIME_ORIGINAL,
            SFE_RUNTIME_HARDENED,
            "SFE runtime state handling",
        )
        runtime_network.write_text(network_content, encoding="utf-8", newline="\n")

    xz_makefile = source / "trunk" / "tools" / "mksquashfs_xz" / "Makefile"
    if xz_makefile.is_file():
        xz_content = xz_makefile.read_text(encoding="utf-8")
        xz_content = replace_exact_once(
            xz_content,
            "build_xz:\n\tmake -C $(SRC_NAME2)",
            "build_xz:\n\tsed -i 's/ po / /g' $(SRC_NAME2)/Makefile\n\tmake -C $(SRC_NAME2)",
            "xz build recipe",
        )
        xz_makefile.write_text(xz_content, encoding="utf-8", newline="\n")

    mkimage = source / "trunk" / "tools" / "mkimage" / "mkimage.c"
    if mkimage.is_file():
        mkimage_content = mkimage.read_text(encoding="utf-8")
        mkimage_content = replace_exact_once(
            mkimage_content,
            "hdr->ih_time  = htonl(sbuf.st_mtime);",
            'hdr->ih_time  = htonl(getenv("SOURCE_DATE_EPOCH") '
            '? strtoul(getenv("SOURCE_DATE_EPOCH"), NULL, 10) : sbuf.st_mtime);',
            "mkimage timestamp assignment",
        )
        mkimage.write_text(mkimage_content, encoding="utf-8", newline="\n")

    openssl_makefile = source / "trunk" / "libs" / "libssl" / "Makefile"
    if openssl_makefile.is_file():
        openssl_content = openssl_makefile.read_text(encoding="utf-8")
        openssl_content = replace_exact_once(
            openssl_content,
            "SRC_NAME=openssl-1.1.1k",
            "SRC_NAME=openssl-1.1.1w",
            "OpenSSL source version",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "SRC_URL=https://www.openssl.org/source/$(SRC_NAME).tar.gz",
            "SRC_URL=https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/$(SRC_NAME).tar.gz",
            "OpenSSL source URL",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "download_test:\n"
            "\t( if [ ! -f $(SRC_NAME).tar.gz ]; then \\\n"
            "\t\twget -t5 --timeout=20 --no-check-certificate -O $(SRC_NAME).tar.gz $(SRC_URL); \\\n"
            "\tfi )",
            "download_test:\n\ttest -f $(SRC_NAME).tar.gz",
            "OpenSSL download recipe",
        )
        openssl_content = replace_exact_once(
            openssl_content,
            "\t\ttar -xf $(SRC_NAME).tar.gz; \\\n\t\tpatch -d $(SRC_NAME) -p1 < $(SRC_NAME).patch; \\\n",
            "\t\ttar -xf $(SRC_NAME).tar.gz; \\\n",
            "OpenSSL extraction patch recipe",
        )
        openssl_makefile.write_text(openssl_content, encoding="utf-8", newline="\n")


def verify_source_policy(source: Path, report: Path) -> dict[str, object]:
    runtime_defaults = source / "trunk" / "user" / "shared" / "defaults.c"
    runtime_network = source / "trunk" / "user" / "rc" / "net.c"
    if not runtime_defaults.is_file() or not runtime_network.is_file():
        raise FirmwareError("prepared source is missing the RM2100 runtime policy files")

    defaults_content = runtime_defaults.read_text(encoding="utf-8")
    network_content = runtime_network.read_text(encoding="utf-8")
    checks = {
        "SFE default mode": defaults_content.count(SFE_DEFAULT_ENABLED) == 1
        and SFE_DEFAULT_DISABLED not in defaults_content,
        "CPU watchdog default": defaults_content.count('\t{ "watchdog_cpu", "1" },') == 1,
        "SFE module state handling": network_content.count(SFE_RUNTIME_HARDENED) == 1
        and SFE_RUNTIME_ORIGINAL not in network_content,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FirmwareError(f"runtime source policy failed: {', '.join(failed)}")

    document: dict[str, object] = {
        "schema": 1,
        "sfe": {
            "default_mode": 1,
            "bridge_ingress_bypass": False,
            "module_state_rechecked": True,
            "conntrack_fallback_on_load_failure": True,
        },
        "watchdog": {"default_enabled": True},
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def parse_kernel_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    unset_pattern = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        unset = unset_pattern.fullmatch(line)
        if unset:
            key, value = unset.group(1), "n"
        elif line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        if key in values:
            raise FirmwareError(f"{path}:{line_number}: duplicate kernel option {key}")
        values[key] = value
    return values


def verify_kernel_config(
    path: Path, cpu_frequency: str, report: Path
) -> dict[str, object]:
    if cpu_frequency not in CPU_FREQUENCIES:
        raise FirmwareError("CPU frequency must be bootloader or 900")
    values = parse_kernel_config(path)
    expected = dict(KERNEL_BASELINE)
    expected["CONFIG_RALINK_MT7621_PLL900"] = CPU_FREQUENCIES[cpu_frequency]
    failed = [
        f"{key}={expected_value} (found {values.get(key, 'missing')})"
        for key, expected_value in expected.items()
        if values.get(key) != expected_value
    ]
    if failed:
        raise FirmwareError(f"kernel performance baseline failed: {', '.join(failed)}")

    document: dict[str, object] = {
        "schema": 1,
        "kernel": "3.4",
        "cpu": {
            "selection": cpu_frequency,
            "forced_frequency_mhz": 900 if cpu_frequency == "900" else None,
            "logical_cpus": 4,
            "smp": True,
        },
        "scheduler": {"hz": 250, "preemption": "none"},
        "network_acceleration": {
            "sfe": True,
            "conntrack_events": True,
            "rps": True,
            "xps": True,
        },
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_image(
    image: Path,
    manifest: Path,
    profile: Path,
    source_commit: str,
    builder_commit: str,
    expected_timestamp: int,
) -> dict[str, object]:
    profile_values = validate_profile(profile)
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise FirmwareError("source commit must be a full lowercase Git SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", builder_commit):
        raise FirmwareError("builder commit must be a full lowercase Git SHA")

    content = image.read_bytes()
    if len(content) <= IMAGE_HEADER.size:
        raise FirmwareError("firmware image is too small")
    header = content[: IMAGE_HEADER.size]
    payload = content[IMAGE_HEADER.size :]
    (
        magic,
        header_crc,
        timestamp,
        data_size,
        load_address,
        entry_point,
        data_crc,
        operating_system,
        architecture,
        image_type,
        compression,
        tail,
        kernel_size,
    ) = IMAGE_HEADER.unpack(header)

    header_for_crc = header[:4] + b"\0\0\0\0" + header[8:]
    checks = {
        "magic": magic == IMAGE_MAGIC,
        "header CRC": zlib.crc32(header_for_crc) == header_crc,
        "data size": data_size == len(payload),
        "data CRC": zlib.crc32(payload) == data_crc,
        "firmware size": MIN_IMAGE_SIZE <= len(content) <= MAX_IMAGE_SIZE,
        "kernel size": 0 < kernel_size < data_size,
        "timestamp": timestamp == expected_timestamp,
        "Linux OS": operating_system == 5,
        "MIPS architecture": architecture == 5,
        "kernel image type": image_type == 2,
        "LZMA compression": compression == 3,
        "kernel version": tuple(tail[:2]) == (3, 4),
        "filesystem version": tuple(tail[2:4]) == (3, 9),
        "RM2100 product": tail[4:27].split(b"\0", 1)[0] == b"RM2100",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FirmwareError(f"firmware verification failed: {', '.join(failed)}")

    document: dict[str, object] = {
        "schema": 1,
        "device": "RM2100",
        "kernel": "3.4",
        "filesystem": "3.9",
        "source": {"commit": source_commit},
        "builder": {"commit": builder_commit},
        "profile": {"sha256": sha256_file(profile)},
        "cpu": {
            "selection": cpu_frequency_from_profile(profile_values),
            "forced_frequency_mhz": (
                900 if cpu_frequency_from_profile(profile_values) == "900" else None
            ),
        },
        "wireless": {
            "country_code": profile_values["CONFIG_FIRMWARE_WLAN_COUNTRY_CODE"].strip('"')
        },
        "artifact": {
            "filename": image.name,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "header_crc32": f"{header_crc:08x}",
            "data_crc32": f"{data_crc:08x}",
            "timestamp": timestamp,
            "created_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "load_address": f"0x{load_address:08x}",
            "entry_point": f"0x{entry_point:08x}",
            "kernel_size": kernel_size,
        },
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-profile")
    validate.add_argument("profile", type=Path)

    configure = subparsers.add_parser("configure-profile")
    configure.add_argument("source", type=Path)
    configure.add_argument("output", type=Path)
    configure.add_argument("--cpu-frequency", required=True, choices=CPU_FREQUENCIES)

    credentials = subparsers.add_parser("validate-credentials")
    credentials.add_argument("admin_password_file", type=Path)
    credentials.add_argument("wifi_password_file", type=Path)

    prepare = subparsers.add_parser("prepare-source")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("--profile", required=True, type=Path)
    prepare.add_argument("--admin-password-file", required=True, type=Path)
    prepare.add_argument("--wifi-password-file", required=True, type=Path)

    verify_source = subparsers.add_parser("verify-source-policy")
    verify_source.add_argument("source", type=Path)
    verify_source.add_argument("--report", required=True, type=Path)

    verify = subparsers.add_parser("verify-image")
    verify.add_argument("image", type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--profile", required=True, type=Path)
    verify.add_argument("--source-commit", required=True)
    verify.add_argument("--builder-commit", required=True)
    verify.add_argument("--expected-timestamp", required=True, type=int)

    verify_kernel = subparsers.add_parser("verify-kernel-config")
    verify_kernel.add_argument("kernel_config", type=Path)
    verify_kernel.add_argument("--cpu-frequency", required=True, choices=CPU_FREQUENCIES)
    verify_kernel.add_argument("--report", required=True, type=Path)

    validate_lock = subparsers.add_parser("validate-lock")
    validate_lock.add_argument("lock", type=Path)

    read_lock = subparsers.add_parser("lock-value")
    read_lock.add_argument("lock", type=Path)
    read_lock.add_argument("key")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "validate-profile":
            validate_profile(arguments.profile)
            print(f"valid profile: {arguments.profile}")
            return 0
        if arguments.command == "validate-credentials":
            validate_credentials(arguments.admin_password_file, arguments.wifi_password_file)
            print("valid provisioning credentials")
            return 0
        if arguments.command == "configure-profile":
            configure_profile(arguments.source, arguments.output, arguments.cpu_frequency)
            print(f"configured profile: {arguments.output}")
            return 0
        if arguments.command == "prepare-source":
            prepare_source(
                arguments.source,
                arguments.profile,
                arguments.admin_password_file,
                arguments.wifi_password_file,
            )
            print(f"prepared source: {arguments.source}")
            return 0
        if arguments.command == "verify-image":
            verify_image(
                arguments.image,
                arguments.manifest,
                arguments.profile,
                arguments.source_commit,
                arguments.builder_commit,
                arguments.expected_timestamp,
            )
            print(f"verified firmware: {arguments.image}")
            return 0
        if arguments.command == "verify-source-policy":
            verify_source_policy(arguments.source, arguments.report)
            print(f"verified runtime source policy: {arguments.source}")
            return 0
        if arguments.command == "verify-kernel-config":
            verify_kernel_config(
                arguments.kernel_config, arguments.cpu_frequency, arguments.report
            )
            print(f"verified kernel config: {arguments.kernel_config}")
            return 0
        if arguments.command == "validate-lock":
            load_lock(arguments.lock)
            print(f"valid Source Lock: {arguments.lock}")
            return 0
        if arguments.command == "lock-value":
            print(lock_value(arguments.lock, arguments.key))
            return 0
        raise FirmwareError(f"unknown command: {arguments.command}")
    except (FirmwareError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
