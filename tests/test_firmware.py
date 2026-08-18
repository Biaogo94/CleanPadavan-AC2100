import json
import subprocess
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
FIRMWARE_TOOL = REPOSITORY / "tools" / "firmware.py"


class ProfilePolicyTests(unittest.TestCase):
    def run_profile_validation(self, profile: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "firmware.config"
            profile_path.write_text(profile, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(FIRMWARE_TOOL), "validate-profile", str(profile_path)],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_profile_rejects_a_kernel_other_than_linux_3_4(self) -> None:
        result = self.run_profile_validation(
            "\n".join(
                (
                    "CONFIG_VENDOR=Ralink",
                    "CONFIG_PRODUCT=MT7621",
                    'CONFIG_FIRMWARE_PRODUCT_ID="RM2100"',
                    "CONFIG_LINUXDIR=linux-4.x",
                    "CONFIG_FIRMWARE_INCLUDE_SFE=y",
                )
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("linux-3.4.x", result.stderr)

    def test_profile_accepts_the_rm2100_linux_3_4_sfe_policy(self) -> None:
        result = self.run_profile_validation(
            "\n".join(
                (
                    "CONFIG_VENDOR=Ralink",
                    "CONFIG_PRODUCT=MT7621",
                    'CONFIG_FIRMWARE_PRODUCT_ID="RM2100"',
                    "CONFIG_LINUXDIR=linux-3.4.x",
                    'CONFIG_FIRMWARE_KERNEL_CONFIG="kernel-3.4.x-5.0.config"',
                    "CONFIG_FIRMWARE_WIFI2_DRIVER=4.1",
                    "CONFIG_FIRMWARE_WIFI5_DRIVER=5.0.5.1",
                    'CONFIG_FIRMWARE_WLAN_COUNTRY_CODE="AU"',
                    "CONFIG_FIRMWARE_CPU_900MHZ=n",
                    "CONFIG_FIRMWARE_INCLUDE_SFE=y",
                    "CONFIG_FIRMWARE_ENABLE_IPV6=y",
                    "CONFIG_FIRMWARE_INCLUDE_IPSET=y",
                    "CONFIG_FIRMWARE_INCLUDE_LANG_CN=y",
                    "CONFIG_FIRMWARE_INCLUDE_HTTPS=y",
                    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EC=y",
                    "CONFIG_FIRMWARE_INCLUDE_OPENSSL_EXE=y",
                )
            )
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid profile", result.stdout)

    def test_repository_source_lock_is_valid(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(FIRMWARE_TOOL),
                "validate-lock",
                str(REPOSITORY / "config" / "build-lock.json"),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid Source Lock", result.stdout)

    def test_profile_rejects_any_device_other_than_rm2100(self) -> None:
        result = self.run_profile_validation(
            "\n".join(
                (
                    "CONFIG_VENDOR=Ralink",
                    "CONFIG_PRODUCT=MT7621",
                    'CONFIG_FIRMWARE_PRODUCT_ID="R2100"',
                    "CONFIG_LINUXDIR=linux-3.4.x",
                    "CONFIG_FIRMWARE_INCLUDE_SFE=y",
                )
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RM2100", result.stderr)

    def test_profile_rejects_the_unused_flowoffload_setting(self) -> None:
        result = self.run_profile_validation(
            "\n".join(
                (
                    "CONFIG_VENDOR=Ralink",
                    "CONFIG_PRODUCT=MT7621",
                    'CONFIG_FIRMWARE_PRODUCT_ID="RM2100"',
                    "CONFIG_LINUXDIR=linux-3.4.x",
                    "CONFIG_FIRMWARE_INCLUDE_SFE=y",
                    "CONFIG_FIRMWARE_ENABLE_FLOWOFFLOAD=y",
                )
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIG_FIRMWARE_ENABLE_FLOWOFFLOAD", result.stderr)

    def test_profile_requires_sfe_acceleration(self) -> None:
        result = self.run_profile_validation(
            "\n".join(
                (
                    "CONFIG_VENDOR=Ralink",
                    "CONFIG_PRODUCT=MT7621",
                    'CONFIG_FIRMWARE_PRODUCT_ID="RM2100"',
                    "CONFIG_LINUXDIR=linux-3.4.x",
                )
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CONFIG_FIRMWARE_INCLUDE_SFE", result.stderr)

    def test_repository_profile_is_valid(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(FIRMWARE_TOOL),
                "validate-profile",
                str(REPOSITORY / "config" / "rm2100-3.4.config"),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class PerformancePolicyTests(unittest.TestCase):
    def test_profile_can_render_each_supported_cpu_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for frequency, expected in (("bootloader", "n"), ("900", "y")):
                with self.subTest(frequency=frequency):
                    output = directory / f"profile-{frequency}.config"
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(FIRMWARE_TOOL),
                            "configure-profile",
                            str(REPOSITORY / "config" / "rm2100-3.4.config"),
                            str(output),
                            "--cpu-frequency",
                            frequency,
                        ],
                        cwd=REPOSITORY,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(
                        f"CONFIG_FIRMWARE_CPU_900MHZ={expected}",
                        output.read_text(encoding="utf-8"),
                    )

    def test_kernel_config_must_match_the_requested_cpu_mode_and_baseline(self) -> None:
        base = (
            "CONFIG_RALINK_MT7621=y\n"
            "CONFIG_SMP=y\n"
            "CONFIG_NR_CPUS=4\n"
            "CONFIG_HZ=250\n"
            "CONFIG_PREEMPT_NONE=y\n"
            "CONFIG_SHORTCUT_FE=y\n"
            "CONFIG_NF_CONNTRACK_EVENTS=y\n"
            "CONFIG_RPS=y\n"
            "CONFIG_XPS=y\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            for frequency, pll_line in (
                ("bootloader", "# CONFIG_RALINK_MT7621_PLL900 is not set\n"),
                ("900", "CONFIG_RALINK_MT7621_PLL900=y\n"),
            ):
                with self.subTest(frequency=frequency):
                    kernel_config = directory / f"kernel-{frequency}.config"
                    report = directory / f"performance-{frequency}.json"
                    kernel_config.write_text(base + pll_line, encoding="utf-8")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(FIRMWARE_TOOL),
                            "verify-kernel-config",
                            str(kernel_config),
                            "--cpu-frequency",
                            frequency,
                            "--report",
                            str(report),
                        ],
                        cwd=REPOSITORY,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    document = json.loads(report.read_text(encoding="utf-8"))
                    self.assertEqual(document["cpu"]["selection"], frequency)
                    self.assertTrue(document["network_acceleration"]["sfe"])

    def test_kernel_config_rejects_a_cpu_mode_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            kernel_config = directory / "kernel.config"
            report = directory / "performance.json"
            kernel_config.write_text(
                "CONFIG_RALINK_MT7621=y\n"
                "CONFIG_RALINK_MT7621_PLL900=y\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "verify-kernel-config",
                    str(kernel_config),
                    "--cpu-frequency",
                    "bootloader",
                    "--report",
                    str(report),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CONFIG_RALINK_MT7621_PLL900=n", result.stderr)
            self.assertFalse(report.exists())


class ProvisioningPolicyTests(unittest.TestCase):
    def test_provisioning_rejects_the_universal_admin_password(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            admin_password = directory / "admin-password"
            wifi_password = directory / "wifi-password"
            admin_password.write_text("admin", encoding="utf-8")
            wifi_password.write_text("A-secure-test-wifi-password", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "validate-credentials",
                    str(admin_password),
                    str(wifi_password),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("administrator password", result.stderr)


class SourcePreparationTests(unittest.TestCase):
    def create_base_source(self, directory: Path) -> tuple[Path, Path, Path]:
        source = directory / "source"
        template = source / "trunk" / "configs" / "templates" / "RM2100.config"
        defaults = source / "trunk" / "user" / "shared" / "defaults.h"
        template.parent.mkdir(parents=True)
        defaults.parent.mkdir(parents=True)
        template.write_text("CONFIG_LINUXDIR=linux-3.4.x\n", encoding="utf-8")
        defaults.write_text(
            '#define DEF_WLAN_2G_CC "CN"\n'
            '#define DEF_WLAN_5G_CC "US"\n'
            '#define DEF_WLAN_2G_PSK "1234567890"\n'
            '#define DEF_WLAN_5G_PSK "1234567890"\n'
            '#define DEF_ROOT_PASSWORD "admin"\n',
            encoding="utf-8",
        )
        admin_password = directory / "admin-password"
        wifi_password = directory / "wifi-password"
        admin_password.write_text("Admin-Test-Password-9381", encoding="utf-8")
        wifi_password.write_text("WiFi-Test-Password-2847", encoding="utf-8")
        return source, admin_password, wifi_password

    def run_preparation(
        self, source: Path, admin_password: Path, wifi_password: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(FIRMWARE_TOOL),
                "prepare-source",
                str(source),
                "--profile",
                str(REPOSITORY / "config" / "rm2100-3.4.config"),
                "--admin-password-file",
                str(admin_password),
                "--wifi-password-file",
                str(wifi_password),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_prepare_source_installs_profile_and_provisioned_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source"
            template = source / "trunk" / "configs" / "templates" / "RM2100.config"
            defaults = source / "trunk" / "user" / "shared" / "defaults.h"
            template.parent.mkdir(parents=True)
            defaults.parent.mkdir(parents=True)
            template.write_text("CONFIG_LINUXDIR=linux-3.4.x\n", encoding="utf-8")
            defaults.write_text(
                "\n".join(
                    (
                        '#define DEF_WLAN_2G_CC "CN"',
                        '#define DEF_WLAN_5G_CC "US"',
                        '#define DEF_WLAN_2G_PSK "1234567890"',
                        '#define DEF_WLAN_5G_PSK "1234567890"',
                        '#define DEF_ROOT_PASSWORD "admin"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            admin_value = "Admin-Test-Password-9381"
            wifi_value = "WiFi-Test-Password-2847"
            admin_password = directory / "admin-password"
            wifi_password = directory / "wifi-password"
            admin_password.write_text(admin_value, encoding="utf-8")
            wifi_password.write_text(wifi_value, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "prepare-source",
                    str(source),
                    "--profile",
                    str(REPOSITORY / "config" / "rm2100-3.4.config"),
                    "--admin-password-file",
                    str(admin_password),
                    "--wifi-password-file",
                    str(wifi_password),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                template.read_text(encoding="utf-8"),
                (REPOSITORY / "config" / "rm2100-3.4.config").read_text(encoding="utf-8"),
            )
            rendered_defaults = defaults.read_text(encoding="utf-8")
            self.assertIn(f'#define DEF_ROOT_PASSWORD\t"{admin_value}"', rendered_defaults)
            self.assertEqual(rendered_defaults.count(wifi_value), 2)
            self.assertIn('#define DEF_WLAN_2G_CC\t"AU"', rendered_defaults)
            self.assertIn('#define DEF_WLAN_5G_CC\t"AU"', rendered_defaults)
            self.assertNotIn(admin_value, result.stdout + result.stderr)
            self.assertNotIn(wifi_value, result.stdout + result.stderr)

    def test_prepare_source_restricts_the_management_plane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source"
            template = source / "trunk" / "configs" / "templates" / "RM2100.config"
            shared = source / "trunk" / "user" / "shared"
            template.parent.mkdir(parents=True)
            shared.mkdir(parents=True)
            template.write_text("CONFIG_LINUXDIR=linux-3.4.x\n", encoding="utf-8")
            (shared / "defaults.h").write_text(
                '#define DEF_WLAN_2G_CC "CN"\n'
                '#define DEF_WLAN_5G_CC "US"\n'
                '#define DEF_WLAN_2G_PSK "1234567890"\n'
                '#define DEF_WLAN_5G_PSK "1234567890"\n'
                '#define DEF_ROOT_PASSWORD "admin"\n',
                encoding="utf-8",
            )
            defaults = shared / "defaults.c"
            defaults.write_text(
                '\t{ "http_access", "0" },\n'
                '\t{ "http_proto", "0" },\n'
                '\t{ "sshd_enable", "1" },\n'
                '\t{ "sfe_enable", "0" },\n',
                encoding="utf-8",
            )
            admin_password = directory / "admin-password"
            wifi_password = directory / "wifi-password"
            admin_password.write_text("Admin-Test-Password-9381", encoding="utf-8")
            wifi_password.write_text("WiFi-Test-Password-2847", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "prepare-source",
                    str(source),
                    "--profile",
                    str(REPOSITORY / "config" / "rm2100-3.4.config"),
                    "--admin-password-file",
                    str(admin_password),
                    "--wifi-password-file",
                    str(wifi_password),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered_defaults = defaults.read_text(encoding="utf-8")
            self.assertIn('{ "http_access", "2" }', rendered_defaults)
            self.assertIn('{ "http_proto", "1" }', rendered_defaults)
            self.assertIn('{ "sshd_enable", "0" }', rendered_defaults)
            self.assertIn('{ "sfe_enable", "1" }', rendered_defaults)

    def test_prepare_source_hardens_the_sfe_runtime_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source, admin_password, wifi_password = self.create_base_source(directory)
            shared = source / "trunk" / "user" / "shared"
            defaults = shared / "defaults.c"
            defaults.write_text(
                '\t{ "http_access", "0" },\n'
                '\t{ "http_proto", "0" },\n'
                '\t{ "sshd_enable", "1" },\n'
                '\t{ "sfe_enable", "0" },\n'
                '\t{ "watchdog_cpu", "1" },\n',
                encoding="utf-8",
            )
            network = source / "trunk" / "user" / "rc" / "net.c"
            network.parent.mkdir(parents=True)
            network.write_text(
                '#if defined (USE_SFE)\n'
                '\tint sfe_enable = nvram_get_int("sfe_enable");\n'
                '\tint sfe_loaded = is_module_loaded("fast_classifier");\n\n'
                '\tif (sfe_loaded && !sfe_enable) {\n'
                '\t\tmodule_smart_unload("fast_classifier", 1);\n'
                '\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");\n'
                '\t\tdoSystem("echo 1 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");\n'
                '\t\tsfe_loaded = 0;\n'
                '\t}\n'
                '\tif (sfe_enable && !sfe_loaded) {\n'
                '\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_be_liberal");\n'
                '\t\tdoSystem("echo 0 > /proc/sys/net/netfilter/nf_conntrack_tcp_no_window_check");\n'
                '\t\tmodule_smart_load("fast_classifier", NULL);\n'
                '\t\tsfe_loaded = 1;\n'
                '\t}\n'
                '\tif (sfe_loaded) {\n'
                '\t\tif (sfe_enable == 1)\n'
                '\t\t\tdoSystem("echo 0 > /sys/fast_classifier/skip_to_bridge_ingress");\n'
                '\t\telse if (sfe_enable == 2)\n'
                '\t\t\tdoSystem("echo 1 > /sys/fast_classifier/skip_to_bridge_ingress");\n'
                '\t}\n'
                '#endif\n',
                encoding="utf-8",
            )

            result = self.run_preparation(source, admin_password, wifi_password)

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered_defaults = defaults.read_text(encoding="utf-8")
            rendered_network = network.read_text(encoding="utf-8")
            self.assertIn('{ "sfe_enable", "1" }', rendered_defaults)
            self.assertNotIn("sfe_loaded = 0;", rendered_network)
            self.assertEqual(
                rendered_network.count('sfe_loaded = is_module_loaded("fast_classifier");'),
                3,
            )
            self.assertIn("SFE module load failed", rendered_network)
            self.assertIn("SFE module unload failed", rendered_network)

            report = directory / "runtime-policy.json"
            verification = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "verify-source-policy",
                    str(source),
                    "--report",
                    str(report),
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(verification.returncode, 0, verification.stderr)
            document = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(document["sfe"]["default_mode"], 1)
            self.assertFalse(document["sfe"]["bridge_ingress_bypass"])
            self.assertTrue(document["sfe"]["module_state_rechecked"])
            self.assertTrue(document["watchdog"]["default_enabled"])

    def test_prepare_source_applies_the_xz_gettext_compatibility_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source, admin_password, wifi_password = self.create_base_source(directory)
            makefile = source / "trunk" / "tools" / "mksquashfs_xz" / "Makefile"
            makefile.parent.mkdir(parents=True)
            makefile.write_text(
                "build_xz:\n\tmake -C $(SRC_NAME2)\n\n"
                "build_squashfs:\n\tmake -C $(SRC_NAME1)\n",
                encoding="utf-8",
            )

            result = self.run_preparation(source, admin_password, wifi_password)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "sed -i 's/ po / /g' $(SRC_NAME2)/Makefile",
                makefile.read_text(encoding="utf-8"),
            )

    def test_prepare_source_hardens_the_image_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source, admin_password, wifi_password = self.create_base_source(directory)
            mkimage = source / "trunk" / "tools" / "mkimage" / "mkimage.c"
            mkimage.parent.mkdir(parents=True)
            mkimage.write_text(
                "hdr->ih_magic = htonl(IH_MAGIC);\n"
                "hdr->ih_time  = htonl(sbuf.st_mtime);\n"
                "hdr->ih_size  = htonl(sbuf.st_size);\n"
                '\t\t\t\tsscanf(argv[1], "%d.%d", &tail_pre.kernel.major, '
                "&tail_pre.kernel.minor);\n"
                '\t\t\t\tsscanf(argv[2], "%d.%d%c", &tail_pre.fs.major, '
                "&tail_pre.fs.minor, &tail_pre.sub_fs);   \n",
                encoding="utf-8",
            )

            result = self.run_preparation(source, admin_password, wifi_password)

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered_mkimage = mkimage.read_text(encoding="utf-8")
            self.assertIn('getenv("SOURCE_DATE_EPOCH")', rendered_mkimage)
            self.assertIn('strtoul(getenv("SOURCE_DATE_EPOCH")', rendered_mkimage)
            self.assertIn('sscanf(argv[1], "%hhu.%hhu"', rendered_mkimage)
            self.assertIn('sscanf(argv[2], "%hhu.%hhu%c"', rendered_mkimage)
            self.assertIn("!= 2", rendered_mkimage)
            self.assertIn("< 2", rendered_mkimage)
            self.assertNotIn('sscanf(argv[1], "%d.%d"', rendered_mkimage)
            self.assertNotIn('sscanf(argv[2], "%d.%d%c"', rendered_mkimage)

    def test_prepare_source_requires_the_locked_openssl_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source, admin_password, wifi_password = self.create_base_source(directory)
            makefile = source / "trunk" / "libs" / "libssl" / "Makefile"
            makefile.parent.mkdir(parents=True)
            makefile.write_text(
                "SRC_NAME=openssl-1.1.1k\n"
                "SRC_URL=https://www.openssl.org/source/$(SRC_NAME).tar.gz\n\n"
                "download_test:\n"
                "\t( if [ ! -f $(SRC_NAME).tar.gz ]; then \\\n"
                "\t\twget -t5 --timeout=20 --no-check-certificate -O $(SRC_NAME).tar.gz $(SRC_URL); \\\n"
                "\tfi )\n\n"
                "extract_test:\n"
                "\t( if [ ! -d $(SRC_NAME) ]; then \\\n"
                "\t\ttar -xf $(SRC_NAME).tar.gz; \\\n"
                "\t\tpatch -d $(SRC_NAME) -p1 < $(SRC_NAME).patch; \\\n"
                "\tfi )\n",
                encoding="utf-8",
            )

            result = self.run_preparation(source, admin_password, wifi_password)

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered_makefile = makefile.read_text(encoding="utf-8")
            self.assertIn("SRC_NAME=openssl-1.1.1w", rendered_makefile)
            self.assertNotIn("wget", rendered_makefile)
            self.assertNotIn("$(SRC_NAME).patch", rendered_makefile)
            self.assertIn("test -f $(SRC_NAME).tar.gz", rendered_makefile)


class FirmwareVerificationTests(unittest.TestCase):
    @staticmethod
    def write_firmware(
        path: Path, timestamp: int = 1623679775, payload_size: int = 4 * 1024 * 1024
    ) -> None:
        payload = (bytes(range(256)) * ((payload_size + 255) // 256))[:payload_size]
        tail = bytes((3, 4, 3, 9)) + b"RM2100".ljust(23, b"\0") + b"\0"
        header = struct.pack(
            ">7I4B28sI",
            0x27051956,
            0,
            timestamp,
            len(payload),
            0x80001000,
            0x802A3A60,
            zlib.crc32(payload),
            5,
            5,
            2,
            3,
            tail,
            0x00140000,
        )
        header_crc = zlib.crc32(header)
        header = header[:4] + struct.pack(">I", header_crc) + header[8:]
        path.write_bytes(header + payload)

    def test_verify_image_emits_a_manifest_for_valid_rm2100_firmware(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            image = directory / "RM2100_3.4.test.trx"
            manifest = directory / "manifest.json"
            self.write_firmware(image)

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "verify-image",
                    str(image),
                    "--manifest",
                    str(manifest),
                    "--profile",
                    str(REPOSITORY / "config" / "rm2100-3.4.config"),
                    "--source-commit",
                    "23387b278a7cf728748af606760758f5d59d1451",
                    "--builder-commit",
                    "0123456789abcdef0123456789abcdef01234567",
                    "--expected-timestamp",
                    "1623679775",
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["device"], "RM2100")
            self.assertEqual(document["kernel"], "3.4")
            self.assertEqual(document["cpu"]["selection"], "bootloader")
            self.assertEqual(document["wireless"]["country_code"], "AU")
            self.assertEqual(document["source"]["commit"], "23387b278a7cf728748af606760758f5d59d1451")
            self.assertEqual(document["artifact"]["size"], image.stat().st_size)
            self.assertEqual(len(document["artifact"]["sha256"]), 64)

    def test_verify_image_rejects_corrupted_payload_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            image = directory / "RM2100_3.4.test.trx"
            manifest = directory / "manifest.json"
            self.write_firmware(image)
            content = image.read_bytes()
            image.write_bytes(content[:-1] + bytes((content[-1] ^ 0xFF,)))

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "verify-image",
                    str(image),
                    "--manifest",
                    str(manifest),
                    "--profile",
                    str(REPOSITORY / "config" / "rm2100-3.4.config"),
                    "--source-commit",
                    "23387b278a7cf728748af606760758f5d59d1451",
                    "--builder-commit",
                    "0123456789abcdef0123456789abcdef01234567",
                    "--expected-timestamp",
                    "1623679775",
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("data CRC", result.stderr)
            self.assertFalse(manifest.exists())

    def test_verify_image_rejects_an_undersized_firmware(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            image = directory / "RM2100_3.4.test.trx"
            manifest = directory / "manifest.json"
            self.write_firmware(image, payload_size=1024)

            result = subprocess.run(
                [
                    sys.executable,
                    str(FIRMWARE_TOOL),
                    "verify-image",
                    str(image),
                    "--manifest",
                    str(manifest),
                    "--profile",
                    str(REPOSITORY / "config" / "rm2100-3.4.config"),
                    "--source-commit",
                    "23387b278a7cf728748af606760758f5d59d1451",
                    "--builder-commit",
                    "0123456789abcdef0123456789abcdef01234567",
                    "--expected-timestamp",
                    "1623679775",
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("size", result.stderr)
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
