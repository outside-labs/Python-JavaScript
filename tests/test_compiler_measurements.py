import gzip
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
SPEC=importlib.util.spec_from_file_location('measure_compiler',ROOT/'scripts/measure_compiler.py')
MEASURE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEASURE)


class CompilerMeasurementTests(unittest.TestCase):
    def test_required_and_full_profile_helpers_match_reference_and_detect_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            entries,expected,records=MEASURE.prepare_conformance(root)
            cases,_=MEASURE.parity.load_cases()
            self.assertEqual(len(records),2*len(cases))
            self.assertEqual({record['helper_policy'] for record in records},{'required','all-profile'})
            selected=next(entry for entry in entries if entry['id']=='numeric-and-unicode-all-profile')
            runtime=root/'conformance'/selected['id']/'runtime.mjs'
            source=runtime.read_text(encoding='utf-8')
            changed=source.replace('return left + right;', 'return left - right;')
            self.assertNotEqual(source,changed)
            runtime.write_text(changed,encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'CPython'):
                MEASURE.verify_results([selected],MEASURE.node_results([selected]),expected)

    def test_complete_payload_map_variants_and_compression_are_accounted(self):
        with tempfile.TemporaryDirectory() as temporary:
            rows=MEASURE.prepare_measurements(Path(temporary),3)
            self.assertEqual(len(rows),12)
            for row,directory,archive in rows:
                with self.subTest(fixture=row['fixture'],variant=row['variant']):
                    counts=row['sizes']
                    buckets=['generated_module_bytes','helper_bytes','source_map_bytes','notice_bytes','metadata_bytes','measurement_harness_bytes']
                    self.assertEqual(sum(counts[name] for name in buckets),counts['complete_payload_bytes'])
                    self.assertEqual(sum(record['gzip_bytes'] for record in row['files']),counts['gzip_file_transfer_bytes'])
                    self.assertEqual(hashlib.sha256(archive).hexdigest(),counts['gzip_tar_sha256'])
                    self.assertEqual(len(gzip.decompress(archive)),counts['canonical_tar_bytes'])
                    self.assertEqual(row['source_map'],any(record['path'].endswith('.map') for record in row['files']))
                    self.assertEqual(counts['interpreter_asset_bytes'],0)
                    self.assertEqual(len(row['build_ns']),3)
                    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as packed:
                        for record in row['files']:
                            data=packed.extractfile(record['path']).read()
                            self.assertEqual(data,(directory/record['path']).read_bytes())
                            self.assertEqual(hashlib.sha256(data).hexdigest(),record['sha256'])
                    if row['fixture'].startswith('text-metrics'):
                        self.assertEqual((directory/'LICENSES/shimify.txt').read_bytes(),MEASURE.parity.LICENSE.read_bytes())
                    if row['helper_policy']=='required':
                        self.assertTrue(row['omitted_profile_helpers'])
                    else:
                        self.assertEqual(row['omitted_profile_helpers'],[])

    def test_sample_bounds_and_output_refusal_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for repeats in [True,0,2,32]:
                with self.subTest(repeats=repeats),self.assertRaises(ValueError):
                    MEASURE.measure(root/'new',repeats=repeats)
            (root/'keep').write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError,'new measurement output'):
                MEASURE.measure(root,repeats=3)
            self.assertEqual((root/'keep').read_bytes(),b'keep')
