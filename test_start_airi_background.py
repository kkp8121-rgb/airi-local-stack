import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
SCRIPT = (ROOT / "start-airi-background.ps1").read_text(encoding="utf-8")


class BackgroundLauncherContractTests(unittest.TestCase):
    def test_requests_background_and_hides_process_window(self) -> None:
        self.assertIn("-ArgumentList @('--background')", SCRIPT)
        self.assertIn("-WindowStyle Hidden", SCRIPT)
        self.assertIn("-PassThru", SCRIPT)

    def test_existing_exact_executable_is_a_noop(self) -> None:
        self.assertIn("[StringComparison]::OrdinalIgnoreCase", SCRIPT)
        self.assertIn("[string]::Equals([string]$_.ExecutablePath", SCRIPT)
        existing_guard = SCRIPT.index("if ($existing.Count -gt 0)")
        launch = SCRIPT.index("$started = Start-Process")
        self.assertLess(existing_guard, launch)
        self.assertIn("'already-running-visible'", SCRIPT[existing_guard:launch])
        self.assertIn("'already-running-hidden'", SCRIPT[existing_guard:launch])
        self.assertIn("return", SCRIPT[existing_guard:launch])

    def test_validates_install_and_passive_renderer_readiness(self) -> None:
        self.assertIn("[IO.Path]::GetFileName($resolvedExecutable) -ine 'AIRI.exe'", SCRIPT)
        self.assertIn("'resources\\app.asar'", SCRIPT)
        self.assertIn("get-airi-local-voice-status.mjs", SCRIPT)
        self.assertIn("return $snapshot.stageMounted -eq $true", SCRIPT)
        self.assertIn("AIRI created a visible window during background startup", SCRIPT)

    def test_never_activates_or_focuses_a_window(self) -> None:
        forbidden = (
            "AppActivate",
            "SetForegroundWindow",
            "ShowWindow",
            "WScript.Shell",
            "send-airi-local-text",
        )
        for token in forbidden:
            self.assertNotIn(token, SCRIPT)

    def test_inspection_mode_precedes_process_launch(self) -> None:
        inspect_guard = SCRIPT.index("if ($InspectOnly)")
        launch = SCRIPT.index("$started = Start-Process")
        self.assertLess(inspect_guard, launch)


if __name__ == "__main__":
    unittest.main()
