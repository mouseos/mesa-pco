#!/usr/bin/env python3
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('build', type=Path, help='configured Mesa host build directory')
parser.add_argument('--base', default='0d94b3f397fb9cf8470bb5600ada8af79ff5361a')
args = parser.parse_args()
root = Path(__file__).resolve().parents[4]
build = args.build.resolve()
commands = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands'], text=True).splitlines()
cc = shlex.split(next(c for c in commands if c.endswith('/pco_opt.c')))
link = shlex.split(next(c for c in commands if ' -o src/imagination/pco/uscgen/pco_clc ' in c))
original = subprocess.check_output(['git', '-C', str(root), 'show', args.base + ':src/imagination/pco/pco_opt.c'])
modified = (root / 'src/imagination/pco/pco_opt.c').read_bytes()
test = Path(__file__).with_name('pco_opt_mods_test.c').read_bytes()
with tempfile.TemporaryDirectory(prefix='pco-opt-mods-') as temp:
    d = Path(temp)
    for name, source in (('base', original), ('candidate', modified)):
        target = d / name
        (target / 'tests').mkdir(parents=True)
        (target / 'pco_opt.c').write_bytes(source)
        (target / 'tests/pco_opt_mods_test.c').write_bytes(test)
        replacements = {'/pco_opt.c': target / 'tests/pco_opt_mods_test.c',
                        '/pco_opt.c.o.d': target / 'test.o.d',
                        '/pco_opt.c.o': target / 'test.o'}
        compile_command = [str(next((v for k, v in replacements.items() if x.endswith(k)), x)) for x in cc]
        subprocess.run(compile_command, cwd=build, check=True)
        link_command = [str(target / 'runner') if x == 'src/imagination/pco/uscgen/pco_clc' else
                        str(target / 'test.o') if x.endswith('/pco_clc.c.o') else x for x in link]
        subprocess.run(link_command, cwd=build, check=True)
    expected = subprocess.check_output([str(d / 'base/runner')])
    for mode in ('normal', 'alloc', 'grow', 'grow2'):
        command = [str(d / 'candidate/runner')]
        if mode != 'normal':
            command.append(mode)
        actual = subprocess.check_output(command)
        if actual != expected:
            raise SystemExit('FAIL: IR differs: ' + mode)
        print('PASS: original and candidate actual PCO IR match:', mode)
