import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY / ".github" / "workflows"


class WorkflowPolicyTests(unittest.TestCase):
    def test_workflows_are_3_4_only_and_pin_every_action(self) -> None:
        workflow_paths = sorted(WORKFLOWS.glob("*.yml"))
        self.assertEqual(
            [path.name for path in workflow_paths],
            ["build.yml"],
        )

        contents = "\n".join(path.read_text(encoding="utf-8") for path in workflow_paths)
        self.assertNotIn("target_version", contents)
        self.assertNotIn("MeIsReallyBa", contents)
        self.assertNotIn("padavan-4.4", contents)
        self.assertIn("scripts/build-firmware.sh", contents)
        self.assertIn("cpu_frequency:", contents)
        self.assertIn("CPU_FREQUENCY:", contents)
        for frequency in ("800", "900", "1000"):
            self.assertIn(f'- "{frequency}"', contents)

        uses_lines = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", contents, re.MULTILINE)
        self.assertTrue(uses_lines)
        for action in uses_lines:
            self.assertRegex(action, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

    def test_build_workflow_separates_read_only_build_from_release(self) -> None:
        build = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", build)
        self.assertIn("release:\n", build)
        self.assertRegex(build, r"release:[\s\S]+?permissions:\n\s+contents: write")
        self.assertIn("environment: production", build)
        self.assertIn("Default WebUI credentials: admin / admin", build)
        self.assertIn("default Wi-Fi password: 1234567890", build)
        self.assertNotIn("Reject public credentialed releases", build)
        self.assertNotIn("Provisioned firmware must not be published from a public repository", build)

    def test_ci_dependency_installation_is_bounded(self) -> None:
        build = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        self.assertIn("run: shellcheck --version", build)
        self.assertNotIn("install --yes --no-install-recommends shellcheck", build)
        self.assertIn("timeout-minutes: 10", build)
        self.assertIn("Acquire::Retries=3", build)
        self.assertIn("Acquire::http::Timeout=30", build)
        self.assertIn("Acquire::https::Timeout=30", build)
        self.assertIn("Dpkg::Lock::Timeout=60", build)
        self.assertIn("/etc/apt/apt-mirrors.txt", build)
        self.assertIn("https://archive.ubuntu.com/ubuntu", build)

    def test_hardware_evidence_collector_is_secret_safe(self) -> None:
        collector = (REPOSITORY / "scripts" / "collect-hardware-evidence.sh").read_text(
            encoding="utf-8"
        )
        workflow = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        self.assertTrue(collector.startswith("#!/bin/sh\n"))
        self.assertIn("snapshot|soak", collector)
        self.assertIn("rt_country_code wl_country_code sfe_enable", collector)
        self.assertIn("/sys/fast_classifier/skip_to_bridge_ingress", collector)
        self.assertIn("/sys/fast_classifier/exceptions", collector)
        self.assertIn("process-status.txt", collector)
        self.assertNotIn("processes.txt", collector)
        self.assertNotIn("ps w", collector)
        self.assertIn("grep -Eiv \"$sensitive\"", collector)
        self.assertIn("samples.tsv", collector)
        self.assertIn("sha256sum", collector)
        self.assertNotIn("nvram show", collector.replace("`nvram show`", ""))
        self.assertNotIn("_password", collector.lower())
        self.assertNotIn("_psk", collector.lower())
        self.assertIn("sh scripts/collect-hardware-evidence.sh --help", workflow)

    def test_firmware_policy_selects_au_and_verifies_the_cpu_variant(self) -> None:
        profile = (REPOSITORY / "config" / "rm2100-3.4.config").read_text(encoding="utf-8")
        build_script = (REPOSITORY / "scripts" / "build-firmware.sh").read_text(
            encoding="utf-8"
        )
        workflow = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        self.assertIn('CONFIG_FIRMWARE_WLAN_COUNTRY_CODE="AU"', profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_900MHZ=n", profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_800MHZ=n", profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_1000MHZ=n", profile)
        self.assertIn('CPU_FREQUENCY="${CPU_FREQUENCY:-bootloader}"', build_script)
        self.assertIn("inputs.cpu_frequency || 'bootloader'", workflow)
        self.assertIn(
            "group: rm2100-3.4-${{ github.ref }}-${{ inputs.cpu_frequency || 'bootloader' }}",
            workflow,
        )
        self.assertIn("configure-profile", build_script)
        self.assertIn("verify-source-policy", build_script)
        self.assertIn("verify-build-log", build_script)
        self.assertIn("verify-kernel-config", build_script)
        self.assertIn("runtime-policy.json", build_script)
        self.assertIn("build-warning-policy.json", build_script)
        self.assertIn("export LC_ALL=C", build_script)
        self.assertIn("export KBUILD_BUILD_TIMESTAMP", build_script)
        self.assertIn("export KBUILD_BUILD_USER=cleanpadavan", build_script)
        self.assertIn("export KBUILD_BUILD_HOST=reproducible", build_script)
        self.assertIn("export KBUILD_BUILD_VERSION=1", build_script)
        self.assertIn("verify-reproducibility", workflow)
        self.assertIn("firmware-rebuild", workflow)
        self.assertIn("BUILD_ROOT: ${{ runner.temp }}/cleanpadavan-build", workflow)
        self.assertIn('rm -rf -- "$RUNNER_TEMP/cleanpadavan-build"', workflow)
        self.assertIn("800|900|1000)", build_script)
        self.assertIn('cpu_variant="cpu-${CPU_FREQUENCY}mhz"', build_script)

    def test_public_defaults_are_used_without_secret_or_random_provisioning(self) -> None:
        build_script = (REPOSITORY / "scripts" / "build-firmware.sh").read_text(
            encoding="utf-8"
        )
        workflow = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        admin = (REPOSITORY / "config" / "default-admin-password").read_text(
            encoding="utf-8"
        ).strip()
        wifi = (REPOSITORY / "config" / "default-wifi-password").read_text(
            encoding="utf-8"
        ).strip()
        self.assertEqual(admin, "admin")
        self.assertEqual(wifi, "1234567890")
        self.assertIn("config/default-admin-password", build_script)
        self.assertIn("config/default-wifi-password", build_script)
        self.assertNotIn("secrets.FIRMWARE_ADMIN_PASSWORD", workflow)
        self.assertNotIn("secrets.FIRMWARE_WIFI_PASSWORD", workflow)
        self.assertNotIn("Ephemeral-", workflow)


if __name__ == "__main__":
    unittest.main()
