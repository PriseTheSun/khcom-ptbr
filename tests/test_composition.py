from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_demo_package import compose
from khcom.errors import KhcomError


class CompositionTests(unittest.TestCase):
    def test_disjoint_edits_compose_and_preserve_other_bytes(self):
        source = b"0123456789"
        target, report = compose(source, [("a", b"01AB456789"), ("b", b"01234567C9")])
        self.assertEqual(target, b"01AB4567C9")
        self.assertEqual([r["changed_bytes"] for r in report], [2, 1])
        self.assertEqual(source, b"0123456789")

    def test_conflicting_or_identical_overlapping_edits_are_rejected(self):
        for second in (b"aBcd", b"aCcd"):
            with self.assertRaises(KhcomError) as caught:
                compose(b"abcd", [("a", b"aBcd"), ("b", second)])
            self.assertEqual(caught.exception.code, "composition_overlap")

    def test_size_change_and_empty_component_do_not_claim_success(self):
        for payload, code in ((b"ab", "composition_size"), (b"abc", "composition_empty")):
            with self.assertRaises(KhcomError) as caught:
                compose(b"abc", [("a", payload)])
            self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
