import copy
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from khcom.errors import KhcomError
from khcom.windows_pe import audit_windows, pe_imports


def authored_pe(normal="KERNEL32.dll", delay="USER32.dll", *, pe32=False, delay_va=False):
    data = bytearray(0x600)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    optional_size = 224 if pe32 else 240
    struct.pack_into("<HHIIIHH", data, 0x84, 0x14C if pe32 else 0x8664, 1, 0, 0, 0, optional_size, 0)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x10B if pe32 else 0x20B)
    struct.pack_into("<I" if pe32 else "<Q", data, optional + (28 if pe32 else 24), 0x400000)
    struct.pack_into("<I", data, optional + 60, 0x200)
    struct.pack_into("<I", data, optional + (92 if pe32 else 108), 16)
    directories = optional + (96 if pe32 else 112)
    section = optional + optional_size
    data[section:section + 5] = b".test"
    struct.pack_into("<IIII", data, section + 8, 0x600, 0x1000, 0x400, 0x200)
    if normal:
        struct.pack_into("<II", data, directories + 8, 0x1000, 40)
        struct.pack_into("<IIIII", data, 0x200, 0, 0, 0, 0x1080, 0)
        name = normal.encode("ascii") + b"\0"
        data[0x280:0x280 + len(name)] = name
    if delay:
        struct.pack_into("<II", data, directories + 8 * 13, 0x1040, 64)
        struct.pack_into("<IIIIIIII", data, 0x240, 0 if delay_va else 1,
                         0x4010C0 if delay_va else 0x10C0, 0, 0, 0, 0, 0, 0)
        name = delay.encode("ascii") + b"\0"
        data[0x2C0:0x2C0 + len(name)] = name
    return bytes(data)


def fixture_package(root, program):
    entries = {"khcom-desktop.exe": (program, "executable"), "notice.txt": (b"authored", "notices"),
               "source.zip": (b"authored", "sources"), "sbom.json": (b"{}", "sbom"),
               "readme.txt": (b"authored", "instructions")}
    manifest = {"schema_version": 1, "kind": "desktop-without-game-data", "platform": "windows",
                "architectures": ["x86_64"], "files": []}
    for name, (data, role) in entries.items():
        (root / name).write_bytes(data)
        manifest["files"].append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "role": role})
    return manifest


class WindowsPETests(unittest.TestCase):
    def test_normal_and_delay_imports_pe32_and_pe32plus_without_loading(self):
        for pe32 in [False, True]:
            for va in [False, True]:
                with self.subTest(pe32=pe32, va=va):
                    result = pe_imports(authored_pe(pe32=pe32, delay_va=va))
                    self.assertEqual(result["machine"], "x86" if pe32 else "x86_64")
                    self.assertEqual(result["imports"], ["KERNEL32.dll"])
                    self.assertEqual(result["delay_imports"], ["USER32.dll"])

    def test_missing_imports_are_explicit_empty_not_inferred_from_bad_header(self):
        result = pe_imports(authored_pe(None, None))
        self.assertEqual(result["imports"], [])
        for raw in [b"", b"MZ" + bytes(62), authored_pe()[:511], authored_pe()[:-1]]:
            with self.subTest(size=len(raw)), self.assertRaises(KhcomError):
                pe_imports(raw)

    def test_rva_zero_fill_unterminated_and_path_imports_fail_closed(self):
        mutations = [lambda d: struct.pack_into("<I", d, 0x20C, 0x1450),
                     lambda d: struct.pack_into("<I", d, 0x98 + 112 + 8 + 4, 20),
                     lambda d: struct.pack_into("<I", d, 0x240, 2),
                     lambda d: struct.pack_into("<I", d, 0x98 + 108, 17),
                     lambda d: struct.pack_into("<I", d, 0x98 + 60, 0x180),
                     lambda d: struct.pack_into("<I", d, 0x98 + 240 + 20, 0x100)]
        for mutate in mutations:
            data = bytearray(authored_pe())
            mutate(data)
            with self.subTest(mutation=mutate), self.assertRaises(KhcomError):
                pe_imports(data)
        for name in ["../kernel32.dll", "C:\\kernel32.dll", "foo/bar.dll", ".bad.dll", "bad..dll"]:
            with self.subTest(name=name), self.assertRaises(KhcomError):
                pe_imports(authored_pe(name))

    def test_overlapping_sections_and_rva_overflow_are_rejected(self):
        data = bytearray(authored_pe())
        struct.pack_into("<H", data, 0x86, 2)
        second = 0x98 + 240 + 40
        struct.pack_into("<IIII", data, second + 8, 0x10, 0x1080, 0x10, 0x500)
        with self.assertRaises(KhcomError):
            pe_imports(data)
        struct.pack_into("<IIII", data, second + 8, 0x100, 0xFFFFFFF0, 0, 0)
        with self.assertRaises(KhcomError):
            pe_imports(data)

    def test_system_resolution_and_api_sets_are_distinct_from_loaded_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, system = root / "package", root / "System32"
            package.mkdir(); system.mkdir()
            manifest = fixture_package(package, authored_pe("KERNEL32.dll", "api-ms-win-core-file-l1-1-0.dll"))
            (system / "KERNEL32.dll").write_bytes(b"authored system stand-in, not loaded")
            result = audit_windows(package, manifest, system)
            self.assertTrue(result["audit_passed"])
            self.assertEqual([x["resolution"] for x in result["dependencies"]], ["system32-file", "api-set-contract-not-a-file"])
            self.assertFalse(result["release_approved"])
            self.assertTrue(result["limitations"])

    def test_delay_missing_and_vc_runtime_installed_on_host_cannot_false_pass(self):
        for name in ["missing.dll", "VCRUNTIME140.dll", "MSVCP140.dll", "ucrtbased.dll"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package, system = root / "package", root / "System32"
                package.mkdir(); system.mkdir()
                manifest = fixture_package(package, authored_pe(None, name))
                if name != "missing.dll":
                    (system / name).write_bytes(b"host-installed redistributable must not hide dependency")
                result = audit_windows(package, manifest, system)
                self.assertFalse(result["audit_passed"])
                self.assertEqual(result["failures"][0]["kind"], "delay_imports")

    def test_local_dll_closure_and_inventory_identity_are_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, system = root / "package", root / "System32"
            package.mkdir(); system.mkdir()
            manifest = fixture_package(package, authored_pe("helper.dll", None))
            helper = authored_pe("api-ms-win-core-file-l1-1-0.dll", None)
            (package / "helper.dll").write_bytes(helper)
            manifest["files"].append({"path": "helper.dll", "role": "executable", "size": len(helper),
                                      "sha256": hashlib.sha256(helper).hexdigest()})
            result = audit_windows(package, manifest, system)
            self.assertTrue(result["audit_passed"])
            self.assertEqual(set(result["images"]), {"khcom-desktop.exe", "helper.dll"})
            changed = copy.deepcopy(manifest)
            changed["files"][-1]["sha256"] = "0" * 64
            with self.assertRaises(KhcomError):
                audit_windows(package, changed, system)

    def test_installer_producer_keeps_per_user_no_data_deletion_contract(self):
        source = (Path(__file__).resolve().parents[1] / "packaging/windows.iss").read_text()
        sections, current = {}, None
        for line in source.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].lower()
                sections.setdefault(current, []).append([])
            elif current:
                sections[current][-1].append(line)
        self.assertEqual(len(sections["setup"]), 1)
        setup = dict(line.split("=", 1) for line in sections["setup"][0])
        self.assertEqual(setup["AppId"], "org.khcom.ptbr.experimental")
        self.assertEqual(setup["PrivilegesRequired"], "lowest")
        self.assertNotIn("PrivilegesRequiredOverridesAllowed", setup)
        self.assertEqual(setup["ArchitecturesAllowed"], "x64compatible")
        self.assertNotIn("uninstalldelete", sections)
        self.assertNotIn("uninstallrun", sections)
        self.assertNotIn("code", sections)
        self.assertNotIn("registry", sections)
        self.assertTrue(all("skipifsilent" in line for group in sections["run"] for line in group))


if __name__ == "__main__":
    unittest.main()
