"""Safety contracts for patch-airi-session-header.ps1.

These tests use only temporary synthetic archives.  They never discover,
open, or change an AIRI installation.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_SCRIPT = ROOT / "patch-airi-session-header.ps1"
POWERSHELL = "powershell.exe"
PRISTINE_HASH = "B3433A29D2E8357A84068DFFCAD80A2A23A4D4C0F5F803764C66839C84B788AF"
PRE_SESSION_HASH = "93DFF73B984A74C71D0BB05F4DC710B8B2DDEDB2724F18D389613995AACD4891"
POST_SESSION_HASH = "CB672061D4A92F36D9450E8A30FE08134D0C66BBC388E1B3C444AD4A328634C8"
POST_SESSION_PRISTINE_HASH = "0E1E4B03D132283F06F6AED743B3AC57C15BEC9C94C942097B00EA236239135C"


class SessionHeaderPatchSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = PATCH_SCRIPT.read_text(encoding="utf-8")

    def run_ps(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_powershell_parser_accepts_script(self) -> None:
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{PATCH_SCRIPT}',[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count){$errors|ForEach-Object{$_.ToString()};exit 1}"
        )
        result = self.run_ps(command)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_exact_version_and_pristine_hash_bindings_are_present(self) -> None:
        self.assertIn("$expectedProductVersion = '0.11.3.0'", self.script)
        self.assertIn(PRISTINE_HASH, self.script)
        self.assertIn(PRE_SESSION_HASH, self.script)
        self.assertIn(POST_SESSION_HASH, self.script)
        self.assertIn(POST_SESSION_PRISTINE_HASH, self.script)
        self.assertIn("VersionInfo.ProductVersion", self.script)
        self.assertIn("Get-FileHash -LiteralPath $Path -Algorithm SHA256", self.script)
        self.assertIn("Pristine backup SHA-256 mismatch", self.script)
        self.assertIn("Unrecognized app.asar marker/hash state", self.script)

    def test_verify_only_requires_marker_and_hash_state_match(self) -> None:
        self.assertIn("$currentHash = Get-Sha256 $resolvedAsar", self.script)
        self.assertIn("ArchiveSha256 = $currentHash", self.script)
        self.assertIn("$state -ne 'unrecognized'", self.script)
        self.assertIn("$knownPostSessionPristineAsarSha256", self.script)
        self.assertIn("$knownPostSessionPreSessionAsarSha256", self.script)
        self.assertIn("$expectedPostHash = if ($currentHash -eq $knownPristineAsarSha256)", self.script)
        self.assertIn("-Force does not override archive-hash checks.", self.script)

    def test_force_warning_does_not_claim_to_bypass_bindings(self) -> None:
        self.assertIn("[switch]$Force", self.script)
        self.assertIn("does not override AIRI version or archive-hash checks.", self.script)
        self.assertIn("-Force does not override this binding.", self.script)

    def test_forced_post_write_verification_failure_rolls_back_synthetic_bytes(self) -> None:
        source_match = re.search(r"Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@", self.script, re.DOTALL)
        self.assertIsNotNone(source_match, "Could not extract the embedded C# patcher")
        csharp = source_match.group(1)
        old = "O" * 332
        new = "N" * 332
        before = b"prefix" + old.encode("ascii") + b"suffix"

        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "synthetic.asar"
            archive.write_bytes(before)
            # The four-argument overload is an isolated test hook; production
            # always calls the three-argument overload with failure disabled.
            harness = Path(temp_dir) / "rollback-test.ps1"
            harness.write_text(
                "$src = @'\n" + csharp + "\n'@\n"
                "Add-Type -TypeDefinition $src\n"
                f"$path = '{archive}'\n"
                f"$old = '{old}'\n$next = '{new}'\n"
                "try {[AiriSessionHeaderPatcher]::Patch($path,$old,$next,$true); exit 9} "
                "catch { if ($_.Exception.Message -notmatch 'verification failed') { throw }; exit 0 }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(archive.read_bytes(), before)

    def test_mixed_stock_and_patched_markers_are_rejected_without_writing(self) -> None:
        source_match = re.search(r"Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@", self.script, re.DOTALL)
        self.assertIsNotNone(source_match)
        old, new = "O" * 332, "N" * 332
        before = b"prefix" + old.encode("ascii") + b"gap" + new.encode("ascii") + b"suffix"
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "synthetic-mixed.asar"
            archive.write_bytes(before)
            harness = Path(temp_dir) / "mixed-marker-test.ps1"
            harness.write_text(
                "$src = @'\n" + source_match.group(1) + "\n'@\nAdd-Type -TypeDefinition $src\n"
                f"$path = '{archive}'\n$old = '{old}'\n$next = '{new}'\n"
                "try {[AiriSessionHeaderPatcher]::Patch($path,$old,$next); exit 9} "
                "catch { if ($_.Exception.Message -notmatch 'Expected exactly one stock') { throw }; exit 0 }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(archive.read_bytes(), before)

    def test_post_hash_mismatch_rolls_back_synthetic_bytes(self) -> None:
        source_match = re.search(r"Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@", self.script, re.DOTALL)
        self.assertIsNotNone(source_match)
        old, new = "O" * 332, "N" * 332
        before = b"prefix" + old.encode("ascii") + b"suffix"
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "synthetic-hash-mismatch.asar"
            archive.write_bytes(before)
            harness = Path(temp_dir) / "hash-mismatch-test.ps1"
            harness.write_text(
                "$src = @'\n" + source_match.group(1) + "\n'@\nAdd-Type -TypeDefinition $src\n"
                f"$path = '{archive}'\n$old = '{old}'\n$next = '{new}'\n"
                "try {[AiriSessionHeaderPatcher]::Patch($path,$old,$next,('0' * 64)); exit 9} "
                "catch { if ($_.Exception.Message -notmatch 'archive hash verification failed') { throw }; exit 0 }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(archive.read_bytes(), before)

    def test_patched_marker_reentry_is_idempotent_on_synthetic_archive(self) -> None:
        source_match = re.search(r"Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@", self.script, re.DOTALL)
        self.assertIsNotNone(source_match)
        old, new = "O" * 332, "N" * 332
        before = b"prefix" + new.encode("ascii") + b"suffix"
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "synthetic-already-patched.asar"
            archive.write_bytes(before)
            harness = Path(temp_dir) / "idempotent-test.ps1"
            harness.write_text(
                "$src = @'\n" + source_match.group(1) + "\n'@\nAdd-Type -TypeDefinition $src\n"
                f"$result = [AiriSessionHeaderPatcher]::Patch('{archive}','{old}','{new}')\n"
                "if ($result -ne 0) { exit 9 }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(archive.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
