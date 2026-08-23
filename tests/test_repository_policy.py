import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY / ".github" / "workflows"
DEFAULT_WORKFLOW = WORKFLOWS / "build-default.yml"
AGGRESSIVE_WORKFLOW = WORKFLOWS / "build-aggressive.yml"


class WorkflowPolicyTests(unittest.TestCase):
    def test_workflows_are_3_4_only_and_pin_every_action(self) -> None:
        workflow_paths = sorted(WORKFLOWS.glob("*.yml"))
        self.assertEqual(
            [path.name for path in workflow_paths],
            ["build-aggressive.yml", "build-default.yml"],
        )

        contents = "\n".join(path.read_text(encoding="utf-8") for path in workflow_paths)
        self.assertNotIn("target_version", contents)
        self.assertNotIn("MeIsReallyBa", contents)
        self.assertNotIn("padavan-4.4", contents)
        self.assertIn("scripts/build-firmware.sh", contents)
        self.assertIn("cpu_frequency:", contents)
        self.assertIn("CPU_FREQUENCY:", contents)
        default = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
        aggressive = AGGRESSIVE_WORKFLOW.read_text(encoding="utf-8")
        for frequency in ("800", "900", "1000"):
            self.assertIn(f'- "{frequency}"', default)
        self.assertIn('options: ["1000"]', aggressive)
        self.assertIn("branches: [main]", default)
        self.assertIn("branches: [main]", aggressive)

        uses_lines = re.findall(r"^\s*-?\s*uses:\s*([^\s#]+)", contents, re.MULTILINE)
        self.assertTrue(uses_lines)
        for action in uses_lines:
            self.assertRegex(action, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

    def test_build_workflow_separates_read_only_build_from_release(self) -> None:
        default = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
        aggressive = AGGRESSIVE_WORKFLOW.read_text(encoding="utf-8")
        for build in (default, aggressive):
            self.assertIn("permissions:\n  contents: read", build)
            self.assertIn("release:\n", build)
            self.assertRegex(build, r"release:[\s\S]+?permissions:\n\s+contents: write")
            self.assertIn("Default WebUI credentials", build)
            self.assertIn("1234567890", build)
            self.assertIn("if: github.event_name == 'workflow_dispatch'", build)
            self.assertIn(
                'RELEASE_VERSION="$(date --utc +%Y%m%d).${GITHUB_RUN_NUMBER}"',
                build,
            )
            self.assertIn('gh release create "$tag" dist/*', build)
            self.assertNotIn("Reject public credentialed releases", build)
            self.assertNotIn(
                "Provisioned firmware must not be published from a public repository",
                build,
            )

        self.assertIn("environment: production", default)
        self.assertNotIn("inputs.publish", default)
        self.assertNotIn("\n      publish:\n", default)
        self.assertNotIn("--prerelease", default)

        self.assertIn("inputs.publish", aggressive)
        self.assertIn("I_UNDERSTAND", aggressive)
        self.assertIn("experimental-profile.json", aggressive)
        self.assertIn("environment: experimental", aggressive)
        self.assertIn("--prerelease", aggressive)
        self.assertIn("--notes-file", aggressive)

    def test_ci_dependency_installation_is_bounded(self) -> None:
        for path in (DEFAULT_WORKFLOW, AGGRESSIVE_WORKFLOW):
            build = path.read_text(encoding="utf-8")
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
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (DEFAULT_WORKFLOW, AGGRESSIVE_WORKFLOW)
        )
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
        self.assertEqual(
            workflows.count("sh scripts/collect-hardware-evidence.sh --help"),
            2,
        )

    def test_firmware_policy_selects_au_and_verifies_the_cpu_variant(self) -> None:
        profile = (REPOSITORY / "config" / "rm2100-3.4.config").read_text(encoding="utf-8")
        build_script = (REPOSITORY / "scripts" / "build-firmware.sh").read_text(
            encoding="utf-8"
        )
        default = DEFAULT_WORKFLOW.read_text(encoding="utf-8")
        aggressive = AGGRESSIVE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('CONFIG_FIRMWARE_WLAN_COUNTRY_CODE="AU"', profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_900MHZ=n", profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_800MHZ=n", profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_1000MHZ=n", profile)
        self.assertIn('CPU_FREQUENCY="${CPU_FREQUENCY:-bootloader}"', build_script)
        self.assertIn("inputs.cpu_frequency || 'bootloader'", default)
        self.assertIn("inputs.cpu_frequency || '1000'", aggressive)
        self.assertIn("rm2100-3.4-aggressive.config", aggressive)
        self.assertIn("EXPERIMENTAL_PROFILE_FILE", aggressive)
        self.assertIn('"${EXPERIMENTAL_ARGS[@]}"', build_script)
        self.assertIn(
            "rm2100-3.4-aggressive.config requires EXPERIMENTAL_PROFILE_FILE",
            build_script,
        )
        self.assertIn(
            "group: rm2100-3.4-${{ github.ref }}-${{ inputs.cpu_frequency || 'bootloader' }}",
            default,
        )
        self.assertIn(
            "group: rm2100-3.4-aggressive-${{ github.ref }}-${{ inputs.cpu_frequency || '1000' }}",
            aggressive,
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
        for workflow in (default, aggressive):
            self.assertIn("verify-reproducibility", workflow)
            self.assertIn("Upload reproducibility diagnostics", workflow)
            self.assertIn("if: failure()", workflow)
            self.assertIn("retention-days: 3", workflow)
            self.assertIn("firmware-rebuild", workflow)
            self.assertIn("BUILD_ROOT: ${{ runner.temp }}/cleanpadavan-build", workflow)
            self.assertIn('rm -rf -- "$RUNNER_TEMP/cleanpadavan-build"', workflow)
        self.assertIn("800|900|1000)", build_script)
        self.assertIn('cpu_variant="cpu-${CPU_FREQUENCY}mhz"', build_script)

    def test_public_defaults_are_used_without_secret_or_random_provisioning(self) -> None:
        build_script = (REPOSITORY / "scripts" / "build-firmware.sh").read_text(
            encoding="utf-8"
        )
        workflows = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (DEFAULT_WORKFLOW, AGGRESSIVE_WORKFLOW)
        )
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
        self.assertNotIn("secrets.FIRMWARE_ADMIN_PASSWORD", workflows)
        self.assertNotIn("secrets.FIRMWARE_WIFI_PASSWORD", workflows)
        self.assertNotIn("Ephemeral-", workflows)

    def test_readme_documents_both_build_modes(self) -> None:
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        self.assertIn("Build RM2100 Padavan 3.4 (Default)", readme)
        self.assertIn("Build RM2100 Padavan 3.4 (Aggressive - Experimental)", readme)
        self.assertIn("build-default.yml", readme)
        self.assertIn("build-aggressive.yml", readme)
        self.assertIn("hw_nat_mode=4", readme)
        self.assertIn("admin", readme)
        self.assertIn("1234567890", readme)
        self.assertIn("-default", readme)
        self.assertIn("-aggressive-o3", readme)


if __name__ == "__main__":
    unittest.main()
