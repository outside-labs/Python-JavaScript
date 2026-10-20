import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


CORPUS = Path(__file__).parent / "fixtures" / "compiler_contract.json"


class CompilerContractTests(unittest.TestCase):
    def test_reference_behavior_and_feature_boundaries(self):
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        entries = corpus["cases"] + corpus["boundaries"]
        self.assertEqual(len({entry["id"] for entry in entries}), len(entries))
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                result = subprocess.run(
                    [sys.executable, "-I", "-c", case["source"]],
                    capture_output=True, text=True, encoding="utf-8", timeout=5,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.replace("\r\n", "\n"), case["stdout"])
        for case in corpus["boundaries"]:
            with self.subTest(boundary=case["id"]):
                self.assertIn(case["classification"], {"rejected", "deferred"})
                self.assertIn(case["diagnostic"], {"PJS100", "PJS110", "PJS120"})
                ast.parse(case["source"])
