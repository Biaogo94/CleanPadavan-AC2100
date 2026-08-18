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
            ["build.yml", "ci.yml"],
        )

        contents = "\n".join(path.read_text(encoding="utf-8") for path in workflow_paths)
        self.assertNotIn("target_version", contents)
        self.assertNotIn("MeIsReallyBa", contents)
        self.assertNotIn("padavan-4.4", contents)
        self.assertIn("scripts/build-firmware.sh", contents)

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


if __name__ == "__main__":
    unittest.main()
