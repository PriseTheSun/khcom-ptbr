import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_patch import provenance
from reconstruct_recipe import validate_recipe
from khcom.errors import KhcomError


class RecipeTests(unittest.TestCase):
    def test_each_literal_needs_nonoverlapping_producer(self):
        literals = [{"target_start": 10, "length": 2, "sha256": "a" * 64}]
        source = [{"component": "credits-fonts", "changed_spans": [[10, 12]]}]
        self.assertFalse(provenance(literals, source)[0]["public_literal_approved"])
        source[0]["component"] = "sora-dialogue"
        self.assertTrue(provenance(literals, source)[0]["public_literal_approved"])
        for bad in [[], [{"component": "sora-dialogue", "changed_spans": [[10, 11]]}], source + source]:
            with self.assertRaises(KhcomError):
                provenance(literals, bad)

    def test_recipe_rejects_embedded_payload_arbitrary_command_and_stale_builder(self):
        recipe = {"schema_version": 1, "recipe": "khcom-ptbr-pilots", "recipe_version": 2,
                  "source_sha256": "a" * 64, "target_sha256": "b" * 64, "patch_sha256": "c" * 64,
                  "builders": {"source.py": "d" * 64}, "contains_original_payload": False, "full_translation": False}
        validate_recipe(recipe, recipe["builders"])
        for mutation in [lambda r: r.update(command="arbitrary command"), lambda r: r.update(payload="bytes"),
                         lambda r: r.update(recipe_version=4), lambda r: r.update(full_translation=True),
                         lambda r: r.update(builders={})]:
            bad = copy.deepcopy(recipe)
            mutation(bad)
            with self.assertRaises(KhcomError):
                validate_recipe(bad, recipe["builders"])


if __name__ == "__main__":
    unittest.main()
