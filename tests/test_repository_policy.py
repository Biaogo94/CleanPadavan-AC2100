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
        self.assertIn('REPOSITORY_VISIBILITY: ${{ github.event.repository.visibility }}', build)
        self.assertIn("Provisioned firmware must not be published from a public repository", build)

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

    def test_firmware_policy_selects_au_and_verifies_the_cpu_variant(self) -> None:
        profile = (REPOSITORY / "config" / "rm2100-3.4.config").read_text(encoding="utf-8")
        build_script = (REPOSITORY / "scripts" / "build-firmware.sh").read_text(
            encoding="utf-8"
        )
        workflow = (WORKFLOWS / "build.yml").read_text(encoding="utf-8")
        self.assertIn('CONFIG_FIRMWARE_WLAN_COUNTRY_CODE="AU"', profile)
        self.assertIn("CONFIG_FIRMWARE_CPU_900MHZ=n", profile)
        self.assertIn('CPU_FREQUENCY="${CPU_FREQUENCY:-bootloader}"', build_script)
        self.assertIn("inputs.cpu_frequency || 'bootloader'", workflow)
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
        self.assertIn("cpu-900mhz", build_script)


if __name__ == "__main__":
    unittest.main()
