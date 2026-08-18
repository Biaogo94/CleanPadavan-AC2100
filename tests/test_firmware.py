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

    def write_userland_policy_sources(self, source: Path) -> dict[str, Path]:
        contents = {
            "rc": (
                "trunk/user/rc/rc.c",
                '#include "rc.h"\n#include "gpio_pins.h"\n'
                "\tset_cpu_affinity(is_ap_mode);\n",
            ),
            "smp": (
                "trunk/user/rc/smp.c",
                "\t{ GIC_IRQ_FE,    SMP_MASK_CPU1 },\n"
                "\t{ GIC_IRQ_PCIE0, SMP_MASK_CPU2 },\n"
                "\t{ GIC_IRQ_PCIE1, SMP_MASK_CPU3 },\n"
                "\t\t\trps_queue_set(rps_iflist[j], last_cpu_mask);\n"
                "\t\t\txps_queue_set(rps_iflist[j], last_cpu_mask);\n",
            ),
            "dot1x": (
                "trunk/user/802.1x/rtdot1x.c",
                "#include <stdlib.h>\n#include <stdio.h>\n"
                "\t\tif (isdigit(prefix_name[c-1]))\n",
            ),
            "pptp_compat": (
                "trunk/user/accel-pptpd/pptpd-1.3.3/compat.c",
                '#include "compat.h"\n\n#ifndef HAVE_STRLCPY\n'
                "#include <string.h>\n#include <stdio.h>\n",
            ),
            "pptp_relay": (
                "trunk/user/accel-pptpd/pptpd-1.3.3/bcrelay.c",
                '  if (ifin == "") {\n'
                '       syslog(LOG_INFO,"Incoming interface required!");\n'
                "       showusage(argv[0]);\n"
                "       _exit(1);\n"
                "  }\n"
                '  if (ifout == "" && ipsec == "") {\n'
                "       showusage(argv[0]);\n"
                "       _exit(1);\n"
                "  } else {\n"
                '        sprintf(interfaces,"%s|%s", ifin, ifout);\n'
                "  }\n"
                '    } else if (ipsec != "" && '
                'strncmp(ifs.ifc_req[i].ifr_name, "ipsec", 5) == 0) {\n',
            ),
            "lanauth": (
                "trunk/user/lanauth/lanauth.c",
                "\tif (!pass || !*pass) usage();\n",
            ),
            "udpxy": (
                "trunk/user/udpxy/util.c",
                'static char s_sysinfo [80] = "\\0";\n'
                "        (void) snprintf (s_sysinfo, sizeof(s_sysinfo)-1, "
                '"%s %s %s",\n',
            ),
            "ifrename": (
                "trunk/user/wireless_tools/ifrename.c",
                "\t  usage(); \n\tcase 'c':\n",
            ),
            "upnp": (
                "trunk/user/miniupnpd/miniupnpd-2.x/upnpevents.c",
                "\t\t\t\tif(obj->state != EConnecting)\n"
                "\t\t\t\t\tbreak;\n"
                "\t\t\tcase EConnecting:\n",
            ),
            "xl2tpd": (
                "trunk/user/xl2tpd/xl2tpd.c",
                "#ifdef USE_KERNEL\n"
                "                 if (!kernel_support)\n"
                "#endif\n"
                "                    close (c->fd);\n"
                "                    c->fd = -1;\n",
            ),
            "mt7615_single_sku": (
                "trunk/proprietary/rt_wifi/rtpci/5.0.5.1/mt7615/txpwr/single_sku.c",
                "\tUINT8  ucNSS = 0;\n"
                "\tif ((ucPhymode == MODE_HTMIX) || "
                "(ucPhymode == MODE_HTGREENFIELD)) {\n"
                "\t\tucNss = (ucMCS >> 3) + 1;\n"
                "\t\tucMCS &= 0x7;\n"
                "\t}\n"
                "\tcPowerOffset = (fgSE) ? "
                "(pAd->CommonCfg.cTxPowerCompBackup[ucBandIdx][ucRateOffset]"
                "[ucNSS - 1]) : "
                "(pAd->CommonCfg.cTxPowerCompBackup[ucBandIdx][ucRateOffset][3]);\n",
            ),
            "busybox_split": (
                "trunk/user/busybox/busybox-1.24.x/scripts/basic/split-include.c",
                "\t    fgets(old_line, buffer_size, fp_target);\n",
            ),
            "busybox_conf": (
                "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/conf.c",
                "\tcase ask_all:\n\t\tfflush(stdout);\n"
                "\t\tfgets(line, 128, stdin);\n\t\treturn;\n"
                "\t\tcase ask_all:\n\t\t\tfflush(stdout);\n"
                "\t\t\tfgets(line, 128, stdin);\n\t\t\tstrip(line);\n",
            ),
            "busybox_mconf": (
                "trunk/user/busybox/busybox-1.24.x/scripts/kconfig/mconf.c",
                "\tpipe(pipefd);\n"
                "static void show_textbox(const char *title, const char *text, int r, int c)\n"
                "{\n\tint fd;\n\n\tfd = creat(\".help.tmp\", 0777);\n"
                "\twrite(fd, text, strlen(text));\n",
            ),
            "busybox_usage": (
                "trunk/user/busybox/busybox-1.24.x/applets/usage.c",
                "\tfor (i = 0; i < num_messages; i++)\n"
                "\t\twrite(STDOUT_FILENO, usage_array[i].usage, "
                "strlen(usage_array[i].usage) + 1);\n",
            ),
            "busybox_tables": (
                "trunk/user/busybox/busybox-1.24.x/applets/applet_tables.c",
                "\tif (argv[2]) {\n"
                "\t\tchar line_old[80];\n"
                "\t\tchar line_new[80];\n"
                "\t\tFILE *fp;\n\n"
                "\t\tline_old[0] = 0;\n"
                "\t\tfp = fopen(argv[2], \"r\");\n"
                "\t\tif (fp) {\n"
                "\t\t\tfgets(line_old, sizeof(line_old), fp);\n"
                "\t\t\tfclose(fp);\n"
                "\t\t}\n"
                "\t\tsprintf(line_new, \"#define NUM_APPLETS %u\\n\", NUM_APPLETS);\n"
                "\t\tif (strcmp(line_old, line_new) != 0) {\n"
                "\t\t\tfp = fopen(argv[2], \"w\");\n"
                "\t\t\tif (!fp)\n"
                "\t\t\t\treturn 1;\n"
                "\t\t\tfputs(line_new, fp);\n"
                "\t\t}\n"
                "\t}\n\n"
                "\treturn 0;\n}\n",
            ),
        }
        paths: dict[str, Path] = {}
        for name, (relative_path, content) in contents.items():
            path = source / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            paths[name] = path
        return paths

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
            self.write_userland_policy_sources(source)

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
            self.assertTrue(
                document["network_distribution"]["mt7621_irq_affinity_verified"]
            )
            self.assertTrue(
                document["network_distribution"]["rps_xps_queue_policy_verified"]
            )
            self.assertEqual(document["userland_hardening"]["exact_source_patches"], 13)
            self.assertEqual(document["wireless_hardening"]["exact_source_patches"], 2)
            self.assertTrue(
                document["wireless_hardening"]["spatial_stream_index_validated"]
            )
            self.assertEqual(
                document["wireless_hardening"]["invalid_spatial_stream_fallback"], 1
            )
            self.assertEqual(document["host_build_hardening"]["exact_source_patches"], 7)
            self.assertTrue(
                document["host_build_hardening"]["generated_output_close_checked"]
            )
            self.assertTrue(document["watchdog"]["default_enabled"])

    def test_prepare_source_hardens_default_userland_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source, admin_password, wifi_password = self.create_base_source(directory)
            paths = self.write_userland_policy_sources(source)

            result = self.run_preparation(source, admin_password, wifi_password)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("#include <flash_mtd.h>", paths["rc"].read_text(encoding="utf-8"))
            dot1x = paths["dot1x"].read_text(encoding="utf-8")
            self.assertIn("#include <ctype.h>", dot1x)
            self.assertIn("isdigit((unsigned char)prefix_name[c-1])", dot1x)
            compat = paths["pptp_compat"].read_text(encoding="utf-8")
            self.assertLess(
                compat.index("#include <string.h>"),
                compat.index("#ifndef HAVE_STRLCPY"),
            )
            relay = paths["pptp_relay"].read_text(encoding="utf-8")
            self.assertNotIn('ifin == ""', relay)
            self.assertNotIn('ipsec != ""', relay)
            self.assertIn("snprintf(interfaces, sizeof(interfaces)", relay)
            self.assertIn("Interface filter is too long", relay)
            self.assertIn(
                "if (!*pass) usage();",
                paths["lanauth"].read_text(encoding="utf-8"),
            )
            udpxy = paths["udpxy"].read_text(encoding="utf-8")
            self.assertIn("s_sysinfo [200]", udpxy)
            self.assertIn("snprintf (s_sysinfo, sizeof(s_sysinfo),", udpxy)
            self.assertIn(
                "usage(); \n\t  break;",
                paths["ifrename"].read_text(encoding="utf-8"),
            )
            self.assertIn("/* fall through */", paths["upnp"].read_text(encoding="utf-8"))
            xl2tpd = paths["xl2tpd"].read_text(encoding="utf-8")
            self.assertIn("if (!kernel_support) {", xl2tpd)
            self.assertIn("                 }\n#endif", xl2tpd)
            single_sku = paths["mt7615_single_sku"].read_text(encoding="utf-8")
            self.assertIn("ucNss > SKU_TX_SPATIAL_STREAM_NUM", single_sku)
            self.assertIn("ucNSS = ucNss - 1;", single_sku)
            self.assertIn("[ucRateOffset][ucNSS]", single_sku)
            self.assertNotIn("[ucRateOffset][ucNSS - 1]", single_sku)
            split_include = paths["busybox_split"].read_text(encoding="utf-8")
            self.assertIn("&& ferror(fp_target)", split_include)
            busybox_conf = paths["busybox_conf"].read_text(encoding="utf-8")
            self.assertEqual(busybox_conf.count("if (!fgets(line, 128, stdin))"), 2)
            busybox_mconf = paths["busybox_mconf"].read_text(encoding="utf-8")
            self.assertIn("if (pipe(pipefd))", busybox_mconf)
            self.assertIn("if (write(fd, text, len) != len)", busybox_mconf)
            busybox_usage = paths["busybox_usage"].read_text(encoding="utf-8")
            self.assertIn("!= (ssize_t)len", busybox_usage)
            busybox_tables = paths["busybox_tables"].read_text(encoding="utf-8")
            self.assertIn("&& ferror(fp)", busybox_tables)
            self.assertIn("if (fclose(stdout) != 0)", busybox_tables)

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


class BuildWarningPolicyTests(unittest.TestCase):
    def run_warning_verification(
        self, directory: Path, content: str
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        build_log = directory / "build.log"
        report = directory / "build-warning-policy.json"
        build_log.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(FIRMWARE_TOOL),
                "verify-build-log",
                str(build_log),
                "--report",
                str(report),
            ],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, report

    def test_build_log_allows_audited_legacy_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            result, report = self.run_warning_verification(
                directory,
                "configure.ac: warning: The macro `AC_TRY_COMPILE' is obsolete.\n"
                "legacy.cpp:42: warning: this 'if' clause does not guard... "
                "[-Wmisleading-indentation]\n",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            document = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(document["total_warnings"], 2)
            self.assertEqual(document["legacy_warnings"], 2)
            self.assertEqual(document["high_risk_warnings"], 0)
            self.assertTrue(
                all(count == 0 for count in document["enforced_categories"].values())
            )

    def test_build_log_rejects_high_risk_compiler_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            result, report = self.run_warning_verification(
                directory,
                "rc.c:65: warning: implicit declaration of function 'flash_mtd_read'\n"
                "bcrelay.c:384: warning: comparison with string literal results in "
                "unspecified behavior [-Waddress]\n"
                "mkimage.c: warning: format '%d' expects argument of type 'int *'\n"
                "util.c: warning: output may be truncated [-Wformat-truncation=]\n"
                "state.c: warning: this statement may fall through [-Wimplicit-fallthrough=]\n"
                "queue.c: warning: value may be used uninitialized [-Wmaybe-uninitialized]\n"
                "generator.c: warning: ignoring return value of 'write' declared with "
                "attribute 'warn_unused_result' [-Wunused-result]\n",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("implicit-function-declaration=1", result.stderr)
            self.assertIn("string-literal-address-comparison=1", result.stderr)
            self.assertIn("format-argument-type=1", result.stderr)
            self.assertIn("format-truncation=1", result.stderr)
            self.assertIn("implicit-fallthrough=1", result.stderr)
            self.assertIn("uninitialized=1", result.stderr)
            self.assertIn("ignored-result=1", result.stderr)
            self.assertFalse(report.exists())


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
