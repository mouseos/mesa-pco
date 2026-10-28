#!/usr/bin/env python3
"""Compile the real sampling implementation and exercise its bounded gate."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[4]
source = (root / 'src/imagination/pco/pco_ir.c').read_text()
body = source[source.index('/* Sampled diagnostic only.'):source.index('/**\n * \\brief Runs passes')]
header = root / 'src/imagination/pco/pco_timing.h'
program = '''#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <assert.h>
#include <pthread.h>
#include "pco_timing.h"
''' + body + '''
static void *worker(void *arg) {
 (void)arg; for (int i=0;i<80;i++) { struct pco_timing_state s;
  if (pco_timing_begin(&s)) { uint64_t t=pco_timing_now(); pco_timing_record("sample_pass",t);
   assert(s.used==1 && s.entries[0].calls==1); pco_timing_finish(&s); }
 } return 0;
}
int main(void) {
 struct pco_timing_state state;
 unsetenv("PVR_PIPELINE_TIMING"); assert(!pco_timing_begin(&state));
 setenv("PVR_PIPELINE_TIMING","01",1); assert(!pco_timing_begin(&state));
 setenv("PVR_PIPELINE_TIMING","1",1); assert(pco_timing_begin(&state));
 struct pco_timing_state inner; assert(!pco_timing_begin(&inner));
 uint64_t t=pco_timing_now(); pco_timing_record("sample_pass",t); pco_timing_record("sample_pass",t);
 assert(state.used==1 && state.entries[0].calls==2); pco_timing_finish(&state);
 pthread_t a,b; assert(!pthread_create(&a,0,worker,0)); assert(!pthread_create(&b,0,worker,0));
 pthread_join(a,0); pthread_join(b,0); assert(pco_timing_current==0);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    c = Path(tmp)/'test.c'; exe=Path(tmp)/'test'; c.write_text(program)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-I',str(header.parent),str(c),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
    assert result.stderr.count('boot=unknown') == 3, result.stderr
    assert result.stderr.count('sample_pass') == 3, result.stderr
print('PASS: default off, strict gate, nesting, per-thread samples, counts and bounded records')
