import copy
import json
from pathlib import Path
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.apple_signing import (OLD_NOTICE, Settings, ToolResult, checked, execute, inventory_after,
                                  operation_lock, plan, readiness, receipt, resume, signature_check)
from khcom.errors import KhcomError
from khcom.package import digest

IDENTITY = "A" * 40
TEAM = "ABCDEFGHIJ"
SUBMISSION = "12345678-1234-4234-8234-123456789abc"


def fixture(root, nested=False):
    root.mkdir()
    app = "Game.app"
    macho = struct.pack("<IIIIIIII", 0xFEEDFACF, 0x100000C, 0, 2, 0, 0, 0, 0)
    entries = {f"{app}/Contents/MacOS/game": (macho, "executable"),
               f"{app}/Contents/Info.plist": (plistlib.dumps({"CFBundleExecutable": "game"}), "bundle-metadata"),
               "notices.txt": (b"authored notice", "notices"), "source.zip": (b"authored source", "sources"),
               "sbom.json": (b"{}", "sbom"), "LEIA-ME.txt": (("macOS: " + OLD_NOTICE + "\n").encode(), "instructions")}
    if nested:
        child = f"{app}/Contents/Helpers/Child.app"
        entries[f"{child}/Contents/MacOS/child"] = (macho, "executable")
        entries[f"{child}/Contents/Info.plist"] = (plistlib.dumps({"CFBundleExecutable": "child"}), "bundle-metadata")
    manifest = {"schema_version": 1, "kind": "desktop-without-game-data", "platform": "macos",
                "status": "experimental", "architectures": ["arm64"], "signature": "ad-hoc",
                "release_approved": False, "sources_sha256": digest(b"authored source"),
                "binary_input_sha256": digest(macho), "files": []}
    for name, (data, role) in entries.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest["files"].append({"path": name, "role": role, "size": len(data), "sha256": digest(data)})
    (root / "package-manifest.json").write_text(json.dumps(manifest))
    return manifest


class AppleFixture:
    """Boundary simulator: it does not establish Apple signature/notary behavior."""
    def __init__(self):
        self.calls = []
        self.status = "In Progress"
        self.submits = 0
        self.final_source = None
        self.reject_stage = None

    def __call__(self, argv, stage):
        self.calls.append((stage, argv))
        if stage == self.reject_stage:
            return ToolResult(1, "", "sensitive-auth-diagnostic")
        if stage.startswith("find-") and stage != "find-identity":
            return ToolResult(0, "/mock/" + argv[-1])
        if stage == "find-identity":
            return ToolResult(0, f'1) {IDENTITY} "Developer ID Application: Fixture ({TEAM})"')
        if stage == "sign-inside-out":
            target = Path(argv[-1])
            if target.is_file():
                target.write_bytes(target.read_bytes() + b"authored-signature-fixture")
            else:
                signature = target / "Contents/_CodeSignature/CodeResources"
                signature.parent.mkdir(exist_ok=True)
                signature.write_bytes(b"authored-seal-fixture")
        if stage == "display-signature":
            return ToolResult(0, "", f"Authority=Developer ID Application: Fixture ({TEAM})\nTeamIdentifier={TEAM}\nCodeDirectory flags=0x10000(runtime)\nTimestamp=fixture\n")
        if stage == "display-entitlements":
            return ToolResult(0, plistlib.dumps({}).decode())
        if stage == "notary-archive":
            Path(argv[-1]).write_bytes(b"authored-upload-fixture")
        if stage == "notary-submit":
            self.submits += 1
            return ToolResult(0, json.dumps({"id": SUBMISSION, "status": "In Progress"}))
        if stage == "notary-info":
            return ToolResult(0, json.dumps({"id": SUBMISSION, "status": self.status}))
        if stage == "staple":
            (Path(argv[-1]) / "Contents/CodeResources").write_bytes(b"authored-ticket-fixture")
        if stage == "final-archive":
            self.final_source = Path(argv[-2])
            Path(argv[-1]).write_bytes(b"authored-final-archive-fixture")
        if stage == "reextract-archive":
            shutil.copytree(self.final_source, Path(argv[-1]) / "payload")
        return ToolResult(0)


class AppleSigningTests(unittest.TestCase):
    def test_plan_is_read_only_and_orders_nested_code_inside_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            fixture(root, nested=True)
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            p = plan(root)
            targets = p["sign_targets"]
            self.assertEqual(targets[-1], "Game.app")
            child = "Game.app/Contents/Helpers/Child.app"
            self.assertLess(targets.index(child + "/Contents/MacOS/child"), targets.index(child))
            self.assertLess(targets.index(child), targets.index("Game.app"))
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_readiness_never_infers_credentials_or_identity_from_configuration(self):
        no_identity = lambda argv, stage: ToolResult(0, "0 valid identities found" if stage == "find-identity" else "/mock/tool")
        state = readiness(Settings(IDENTITY, "existing-profile"), no_identity, "darwin")
        self.assertFalse(state["ready_to_attempt"])
        self.assertFalse(state["profile_credentials_verified"])
        self.assertFalse(readiness(Settings(), AppleFixture(), "linux")["ready_to_attempt"])
        with self.assertRaises(KhcomError):
            readiness(Settings("Developer ID Application: fuzzy name"), AppleFixture(), "darwin")
        self.assertTrue(readiness(Settings(IDENTITY, "existing-profile"), AppleFixture(), "darwin")["ready_to_attempt"])

    def test_uninventoried_code_bad_notice_or_source_mutation_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            fixture(root)
            (root / "extra").write_bytes(b"unlisted")
            with self.assertRaises(KhcomError):
                plan(root)
            (root / "extra").unlink()
            p = plan(root)
            (root / "source.zip").write_bytes(b"changed")
            with self.assertRaises(KhcomError) as error:
                inventory_after(root, p)
            self.assertEqual(error.exception.code, "apple_mutation")

    def test_reconciliation_changes_only_signature_regions_and_records_both_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            original = fixture(root)
            p = plan(root)
            exe = root / p["code_files"][0]
            old = digest(exe.read_bytes())
            exe.write_bytes(exe.read_bytes() + b"signature")
            rows, changes = inventory_after(root, p)
            self.assertEqual(changes[0]["before"]["sha256"], old)
            self.assertNotEqual(changes[0]["after"]["sha256"], old)
            self.assertEqual(p["binary_input_sha256"], original["binary_input_sha256"])
            exe.write_bytes(exe.read_bytes() + b"later-code-change")
            with self.assertRaises(KhcomError):
                inventory_after(root, p, signed=rows)

    @patch("khcom.apple_signing.sys.platform", "darwin")
    def test_full_simulated_boundary_preserves_provenance_and_requires_accepted_ticket_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "source", Path(tmp) / "signed"
            original = fixture(root)
            before = (root / "package-manifest.json").read_bytes()
            apple, settings = AppleFixture(), Settings(IDENTITY, "preprovisioned-profile")
            self.assertEqual(execute(root, out, settings, apple)["state"], "submitted")
            self.assertEqual(apple.submits, 1)
            self.assertEqual(resume(out, settings, apple)["state"], "pending")
            self.assertNotIn("staple", [stage for stage, _ in apple.calls])
            apple.status = "Accepted"
            result = resume(out, settings, apple)
            self.assertEqual(result["state"], "notarized-and-stapled")
            self.assertFalse(result["release_approved"])
            self.assertFalse(result["clean_download_gatekeeper_verified"])
            self.assertEqual(apple.submits, 1)
            final = json.loads((out / "payload/package-manifest.json").read_text())
            for key in ("binary_input_sha256", "sources_sha256", "status"):
                self.assertEqual(final[key], original[key])
            self.assertEqual(final["apple_signing"]["input_manifest_sha256"], digest(before))
            self.assertEqual((root / "package-manifest.json").read_bytes(), before)
            self.assertEqual((out / "provenance/input-package-manifest.json").read_bytes(), before)
            self.assertNotIn(OLD_NOTICE, (out / "payload/LEIA-ME.txt").read_text())
            self.assertEqual((root / "source.zip").read_bytes(), (out / "payload/source.zip").read_bytes())
            self.assertTrue(any(stage == "validate-transport-ticket" for stage, _ in apple.calls))
            self.assertTrue(all("--deep" not in argv for stage, argv in apple.calls if stage == "sign-inside-out"))
            with self.assertRaises(KhcomError):
                resume(out, settings, apple)

    @patch("khcom.apple_signing.sys.platform", "darwin")
    def test_rejection_and_missing_receipt_never_staple_or_resubmit(self):
        for outcome in ("Invalid", "missing-receipt"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                root, out = Path(tmp) / "source", Path(tmp) / "signed"
                fixture(root)
                apple, settings = AppleFixture(), Settings(IDENTITY, "profile")
                execute(root, out, settings, apple)
                if outcome == "missing-receipt":
                    (out / "provenance/submission.json").unlink()
                else:
                    apple.status = outcome
                with self.assertRaises(KhcomError):
                    resume(out, settings, apple)
                self.assertEqual(apple.submits, 1)
                self.assertNotIn("staple", [stage for stage, _ in apple.calls])
                self.assertFalse((out / "result.json").exists())

    @patch("khcom.apple_signing.sys.platform", "darwin")
    def test_failed_final_validation_keeps_owned_output_without_false_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "source", Path(tmp) / "signed"
            fixture(root)
            apple, settings = AppleFixture(), Settings(IDENTITY, "profile")
            execute(root, out, settings, apple)
            apple.status, apple.reject_stage = "Accepted", "validate-transport-ticket"
            with self.assertRaises(KhcomError):
                resume(out, settings, apple)
            self.assertFalse((out / "result.json").exists())
            self.assertTrue((out / "payload/package-manifest.json").exists())
            apple.reject_stage = None
            self.assertEqual(resume(out, settings, apple)["state"], "notarized-and-stapled")
            self.assertEqual(apple.submits, 1)

    @patch("khcom.apple_signing.sys.platform", "darwin")
    def test_submission_artifacts_are_bound_and_input_is_never_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "source", Path(tmp) / "signed"
            fixture(root)
            apple, settings = AppleFixture(), Settings(IDENTITY, "profile")
            execute(root, out, settings, apple)
            apple.status = "Accepted"
            (out / "submission.zip").write_bytes(b"different-upload")
            with self.assertRaises(KhcomError) as error:
                resume(out, settings, apple)
            self.assertEqual(error.exception.code, "apple_provenance")
            self.assertNotIn("staple", [stage for stage, _ in apple.calls])
            self.assertEqual(apple.submits, 1)

    def test_owned_operation_lock_excludes_concurrent_resume_and_can_be_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with operation_lock(root):
                with self.assertRaises(KhcomError) as error:
                    with operation_lock(root):
                        self.fail("second lock must fail")
                self.assertEqual(error.exception.code, "apple_busy")
            with operation_lock(root):
                self.assertTrue((root / ".operation.lock").exists())

    @patch("khcom.apple_signing.sys.platform", "darwin")
    def test_not_ready_never_creates_output_or_attempts_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, out = Path(tmp) / "source", Path(tmp) / "signed"
            fixture(root)
            apple = AppleFixture()
            with self.assertRaises(KhcomError) as error:
                execute(root, out, Settings(), apple)
            self.assertEqual(error.exception.code, "apple_not_ready")
            self.assertFalse(out.exists())
            self.assertFalse(any(stage == "sign-inside-out" for stage, _ in apple.calls))
            self.assertEqual(apple.submits, 0)

    def test_signature_evidence_rejects_false_runtime_wrong_team_missing_timestamp_and_grants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            fixture(root)
            p = plan(root)
            for defect in ("flags", "team", "timestamp", "authority", "entitlements"):
                with self.subTest(defect=defect):
                    apple = AppleFixture()
                    def broken(argv, stage):
                        result = apple(argv, stage)
                        if stage == "display-signature":
                            text = result.stderr
                            if defect == "flags": text = text.replace("0x10000(runtime)", "0x0(not-runtime)")
                            if defect == "team": text = text.replace(f"TeamIdentifier={TEAM}", f"TeamIdentifier={TEAM}EXTRA")
                            if defect == "timestamp": text = text.replace("Timestamp=fixture", "Timestamp=none")
                            if defect == "authority": text = text.replace("Authority=Developer ID Application:", "Authority=Apple Development:")
                            return ToolResult(0, "", text)
                        if stage == "display-entitlements" and defect == "entitlements":
                            return ToolResult(0, plistlib.dumps({"com.apple.security.get-task-allow": True}).decode())
                        return result
                    with self.assertRaises(KhcomError):
                        signature_check(root, p, {"codesign": "/mock/codesign"}, TEAM, broken)

    def test_source_digest_is_bound_to_actual_audited_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            original = fixture(root)
            original["sources_sha256"] = "0" * 64
            (root / "package-manifest.json").write_text(json.dumps(original))
            with self.assertRaises(KhcomError) as error:
                plan(root)
            self.assertEqual(error.exception.code, "apple_provenance")

    def test_untrusted_tool_error_never_echoes_auth_diagnostics(self):
        with self.assertRaises(KhcomError) as error:
            checked(lambda argv, stage: ToolResult(7, "private-key-secret", "password-value"), ["tool"], "notary")
        rendered = json.dumps(error.exception.as_dict())
        self.assertNotIn("private-key-secret", rendered)
        self.assertNotIn("password-value", rendered)
        self.assertEqual(error.exception.details["exit_code"], 7)

    def test_receipt_requires_uuid_and_known_status(self):
        for output in ("not-json", '{"id":"not-an-id"}', '{"id":3}', '[]',
                       json.dumps({"id": SUBMISSION, "status": {}}),
                       json.dumps({"id": SUBMISSION, "status": "Maybe"})):
            with self.subTest(output=output), self.assertRaises(KhcomError):
                receipt(ToolResult(0, output))
        with self.assertRaises(KhcomError):
            receipt(ToolResult(0, json.dumps({"id": SUBMISSION})), require_status=True)


if __name__ == "__main__":
    unittest.main()
