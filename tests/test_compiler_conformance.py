import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('compiler_conformance', ROOT / 'scripts/compiler_conformance.py')
SUITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUITE)


class CompilerConformanceTests(unittest.TestCase):
    def test_shared_reference_and_emitted_node_suite(self):
        report = SUITE.conformance()
        cases, boundaries = SUITE.load_cases()
        self.assertEqual(report['suite'], 'compiler-parity/1')
        self.assertEqual(len(report['targets']['node']['cases']), len(cases))
        self.assertEqual(len(report['boundaries']), len(boundaries))
        self.assertEqual({item['status'] for item in report['targets']['node']['cases']}, {'pass'})
        json.dumps(report)

    def test_borrowed_computation_retains_exact_notice_and_record(self):
        cases, _ = SUITE.load_cases()
        borrowed = next(case for case in cases if case['id'] == 'text-metrics-single-module')
        artifact = SUITE.compile_case(dict(borrowed, borrowed=True))
        notice = next(item for item in artifact.files if item.path == 'LICENSES/shimify.txt')
        self.assertEqual(notice.data, SUITE.LICENSE.read_bytes())
        self.assertIn(notice.path, artifact.manifest['notices'])
