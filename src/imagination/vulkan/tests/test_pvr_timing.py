#!/usr/bin/env python3
"""Compile actual pipeline timing gate with a mock output sink."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[4]
s=(root/'src/imagination/vulkan/pvr_arch_pipeline.c').read_text()
body=s[s.index('/* Bounded wall-time samples;'):s.index('/*****************************************************************************\n   PDS functions')]
for name in ('pvr_compute_pipeline_create','pvr_graphics_pipeline_create'):
    at=s.index('const VkResult local_result =\n         '+name)
    assert 'pvr_timing_begin' in s[at-160:at]
    assert 'pvr_timing_end' in s[at:at+450]
program='''#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <assert.h>
typedef int VkResult;
static unsigned lines; static uint64_t now;
static uint64_t pco_timing_now(void){return ++now;}
static void pco_timing_log(const char *s){assert(strlen(s)<64);++lines;}
static void pco_timing_log_boot(void){++lines;}
'''+body+'''
int main(void){unsigned id;uint64_t start;
 unsetenv("PVR_PIPELINE_TIMING"); assert(!pvr_timing_begin(&id,&start,'g') && !now);
 setenv("PVR_PIPELINE_TIMING","01",1); assert(!pvr_timing_begin(&id,&start,'g') && !now);
 setenv("PVR_PIPELINE_TIMING","1",1);
 for(unsigned n=0;n<520;n++) if(pvr_timing_begin(&id,&start,'g')) {assert(id%64==0 && id<512);pvr_timing_end(id,start,-7,'g');}
 assert(lines==24 && now==16);return 0;}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'test.c';e=Path(tmp)/'test';p.write_text(program)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(p),'-o',str(e)],check=True)
 subprocess.run([str(e)],check=True)
print('PASS: both pipeline entry points, strict gate, clock and bounded sample output')
