#!/usr/bin/env python3
"""Test production queue timing gates, boundaries, errors, and output budget."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[4]
source=r'''#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint64_t ticks=1;static unsigned calls,lines;
uint64_t pco_timing_now(void){++calls;return ticks;}
uint64_t pco_timing_tid(void){return 42;}
void pco_timing_log(const char *s){assert(strlen(s)<64);++lines;}
#include "pvr_queue_timing.h"
int main(void){struct pvr_queue_timing t={0};
 unsetenv("PVR_QUEUE_TIMING");pvr_queue_timing_begin(&t);pvr_queue_timing_step(&t,1);pvr_queue_timing_end(&t,0);assert(!calls&&!lines);
 setenv("PVR_QUEUE_TIMING","1",1);t=(struct pvr_queue_timing){0};ticks=1;pvr_queue_timing_begin(&t);ticks=10;pvr_queue_timing_step(&t,1);pvr_queue_timing_end(&t,0);assert(!lines);
 for(unsigned j=0;j<4;j++){t=(struct pvr_queue_timing){0};ticks=1;pvr_queue_timing_begin(&t);for(unsigned i=1;i<=4;i++){ticks+=300000000;pvr_queue_timing_step(&t,i);}pvr_queue_timing_end(&t,0);assert(lines==8*(j+1));}
 t=(struct pvr_queue_timing){0};unsigned c=calls;pvr_queue_timing_begin(&t);pvr_queue_timing_end(&t,0);assert(calls==c&&lines==32);
 pvr_queue_timing_reports=0;t=(struct pvr_queue_timing){0};ticks=0;pvr_queue_timing_begin(&t);pvr_queue_timing_end(&t,1);assert(lines==34);
 return 0;}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/'test.c';e=Path(d)/'test';p.write_text(source)
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(root/'src/imagination'),'-I',str(root/'src/imagination/vulkan'),str(p),'-o',str(e)],check=True)
 subprocess.run([str(e)],check=True)
s=(root/'src/imagination/vulkan/pvr_arch_queue.c').read_text();a=s.rindex('static VkResult pvr_driver_queue_submit(');b=s.index('VkResult PVR_PER_ARCH(QueueBindSparse)',a);s=s[a:b]
assert all('pvr_queue_timing_step(&timing, '+str(n)+')' in s for n in range(1,5))
assert s.count('goto timing_done;')==3 and 'return result;' in s
print('PASS queue timing default-off, slow-only, error, bounded output and phase hooks')
