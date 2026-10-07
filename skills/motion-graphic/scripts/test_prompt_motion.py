"""Focused CLI integration checks. Synthetic fixtures are never business facts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SKILL = Path(__file__).resolve().parent.parent
CLI = SKILL / 'scripts/assemble.py'
ENGINE = SKILL / 'assets/engine.html'
CATALOG = Path('/Users/dongchanyoon/Documents/Work/Projects/15.design_base/catalogs/prompt-motion/catalog.json')


class PromptMotionCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, code=0):
        result = subprocess.run(['python3', str(CLI), *map(str, args)], capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def input_file(self, data, name='input.json'):
        p = self.root / name
        p.write_text(json.dumps(data, ensure_ascii=False))
        return p

    def test_all_46_full_prompt_handoffs_and_automatic_selection(self):
        originals = json.loads(CATALOG.read_text())
        listing = json.loads(self.run_cli('recipes').stdout)
        self.assertEqual({x['slug'] for x in listing}, {x['slug'] for x in originals})
        self.assertEqual(len(listing), 46)
        for item in originals:
            packet = json.loads(self.run_cli('info', '--recipe', item['slug']).stdout)
            self.assertEqual(packet['recipe']['prompt_ko'], item['prompt_ko'])
            self.assertFalse(packet['render_ready'])
            self.assertEqual(packet['input_status'], 'not_provided')
            self.assertEqual(len(packet['recommended_techniques']), 3)
            self.assertTrue(all(x['recipe'] and x['timing'] for x in packet['recommended_techniques']))
            self.assertIn('Copyright (c) 2026 Leonxlnx', packet['license_notice'])
            self.assertIn('Permission is hereby granted', packet['license_notice'])
        auto = json.loads(self.run_cli('info', '--brief', 'text-built-route').stdout)
        self.assertEqual(auto['recipe']['slug'], 'text-built-route')
        media = json.loads(self.run_cli('info', '--brief', 'evidence-lens').stdout)
        self.assertEqual(media['recipe']['slug'], 'evidence-lens')
        self.assertFalse(media['template_support']['supported'])

    def test_variants_generate_distinct_code_and_preserve_shell(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('assemble', CLI)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base = dict(title='검증용 템플릿', duration=12, subtitle='검증용 합성자료')
        row = dict(label='입력', detail='검증용 문장', source='검증용 합성자료', date='2026-10-07')
        fixtures = {
            'route': dict(phrases=['입력을 연결합니다', '근거를 연결합니다', '출력을 연결합니다'], verb='연결'),
            'poster': dict(facts=[row, {**row, 'label': '근거'}]),
            'mask': dict(phrases=['입력을 읽습니다', '개념을 확인합니다'], line_art=[[0, .2], [.5, .8], [1, .3]]),
            'ribbon': dict(steps=[row, {**row, 'label': '검증'}]),
            'decision': dict(steps=[row, {**row, 'label': '검증'}], input_source='검증용 합성자료', sample_input='검증용 입력', verification_step='검증'),
            'recursive': dict(levels=[row, {**row, 'label': '다음 수준'}], stop_condition='두 수준에서 종료'),
            'milestone': dict(events=[row, {**row, 'label': '완료'}], relation_type='검증용 순서'),
            'notes': dict(notes=[row, {**row, 'label': '근거'}], product='검증용 종이', verified_result='두 근거 확인'),
            'drawing': dict(drawings=[dict(label='입력', points=[[0, 0], [1, 1]]), dict(label='출력', points=[[0, 1], [1, 0]])], relations=[dict(from_=0)]),
            'stack': dict(numbers=[dict(label='확인된 0', value=0, unit='개', source='검증용 합성자료'), dict(label='확인된 0', value=0, unit='개', source='검증용 합성자료')]),
            'signal': dict(signal_data=[0, 1, 2, 1, 0, 2, 3, 1], meaning_labels=[row, {**row, 'label': '피크'}], signal_source='검증용 합성자료', signal_kind='synthetic'),
        }
        fixtures['drawing']['relations'] = [{'from': 0, 'to': 1, 'label': '연결'}]
        originals = {x['slug']: x for x in json.loads(CATALOG.read_text())}
        outputs = set()
        for slug, (family, variant) in module.TEMPLATES.items():
            p = self.root / slug
            data = {**base, **fixtures[variant]}
            # Source-name requirements that are not renderer fields stay explicit.
            values = module.source_inputs(data, variant, 'npl')
            data['source_inputs'] = {k: '검증용 합성자료' for k in originals[slug]['inputs'] if values.get(k) is None}
            f = self.input_file(data, slug + '.json')
            packet = json.loads(self.run_cli('info', '--recipe', slug, '--inputs', f).stdout)
            self.assertTrue(packet['render_ready'], slug)
            self.run_cli('split', ENGINE, p, '--recipe', slug, '--inputs', f)
            dst = self.root / (slug + '.html')
            self.run_cli('build', p, dst)
            outputs.add(hashlib.sha256(dst.read_bytes()).hexdigest())
            self.assertIn('Copyright (c) 2026 Leonxlnx', dst.read_text())
            self.assertIn('Permission is hereby granted', dst.read_text())
            def strip_parts(s):
                for name in module.PARTS:
                    s = module.block_re(name).sub(lambda m: m['open'] + m['close'], s)
                return s
            self.assertEqual(strip_parts(dst.read_text()), strip_parts(ENGINE.read_text()))
        self.assertEqual(len(outputs), 11)

    def test_fail_before_mutation_and_preserve_existing_edits(self):
        valid = dict(title='검증용', duration=12, phrases=['연결합니다', '자료를 연결합니다', '근거를 연결합니다'], verb='연결')
        f = self.input_file(valid)
        dest = self.root / 'parts'
        for options in [('--recipe', 'unknown'), ('--recipe', 'text-built-route', '--theme', '../npl'), ('--recipe', 'text-built-route', '--theme', 'missing'), ('--recipe', 'evidence-lens')]:
            self.run_cli('split', ENGINE, dest, *options, '--inputs', f, code=2)
            self.assertFalse(dest.exists())
        bad = self.root / 'bad.json'
        bad.write_text('{bad')
        self.run_cli('split', ENGINE, dest, '--recipe', 'text-built-route', '--inputs', bad, code=2)
        self.assertFalse(dest.exists())
        bad_catalog = self.root / 'bad-source/catalogs/prompt-motion'
        bad_catalog.mkdir(parents=True)
        (bad_catalog / 'catalog.json').write_text('[{"slug":"bad"}]')
        self.run_cli('split', ENGINE, dest, '--recipe', 'bad', '--inputs', f, '--catalog-root', self.root / 'bad-source', code=2)
        self.assertFalse(dest.exists())
        numeric = dict(title='누락', duration=12, numbers=[dict(label='A', unit='개', source='검증용 합성자료'), dict(label='B', value=0, unit='개', source='검증용 합성자료')])
        self.run_cli('split', ENGINE, dest, '--recipe', 'quantity-stack', '--inputs', self.input_file(numeric, 'numeric.json'), code=2)
        self.assertFalse(dest.exists())
        blank = self.input_file({'상태명 목록': '   ', '전환 조건': '입력 확인', '가로 비율': '16:9', '총 길이': 12}, 'blank.json')
        result = json.loads(self.run_cli('info', '--recipe', 'workflow-shape-ribbon', '--inputs', blank, code=2).stdout)
        self.assertIn('상태명 목록', result['missing_inputs'])
        self.run_cli('split', ENGINE, dest, '--recipe', 'text-built-route', '--inputs', f)
        edit = dest / 'scenes.js'
        edit.write_text(edit.read_text() + '\n// owned edit\n')
        before = {p.name: p.read_bytes() for p in dest.iterdir()}
        self.run_cli('split', ENGINE, dest, '--recipe', 'text-built-route', '--inputs', f, code=2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in dest.iterdir()})

    def test_legacy_split_build_and_script_safe_user_text(self):
        legacy = self.root / 'legacy'
        self.run_cli('split', ENGINE, legacy)
        built = self.root / 'legacy.html'
        self.run_cli('build', legacy, built)
        self.assertEqual(built.read_bytes(), ENGINE.read_bytes())
        title = '</script><script>window.__injected=1</script> "따옴표"\n다음 줄'
        data = dict(title=title, duration=12, phrases=['연결합니다', '둘을 연결합니다', '셋을 연결합니다'], verb='연결')
        selected = self.root / 'escaped'
        self.run_cli('split', ENGINE, selected, '--recipe', 'text-built-route', '--inputs', self.input_file(data))
        geometry = (selected / 'geometry.js').read_text()
        parsed = json.loads(geometry.removeprefix('const PM = ').strip().removesuffix(';'))
        self.assertEqual(parsed['input']['title'], title)
        self.assertNotIn('</script>', geometry)


if __name__ == '__main__':
    unittest.main(verbosity=2)
