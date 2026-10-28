#!/usr/bin/env python3
"""Compile the real PCO and pipeline timers with deterministic clocks and output."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parents[4]
pco=(root/'src/imagination/pco/pco_ir.c').read_text()
pco=pco[pco.index('/* Sampled diagnostic only.'):pco.index('/**\n * \\brief Runs passes')]
pvr=(root/'src/imagination/vulkan/pvr_arch_pipeline.c').read_text()
pvr=pvr[pvr.index('/* Bounded wall-time samples.'):pvr.index('/*****************************************************************************\n   PDS functions')]
program=r'''#define _POSIX_C_SOURCE 200809L
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#include <stdarg.h>
#include <assert.h>
#include "pco_timing.h"
typedef int VkResult;
static uint64_t tick=1; static unsigned clock_calls, fail_clock_call;
static char output[65536]; static unsigned nlines;
static int fake_clock(clockid_t clock,struct timespec *t) {(void)clock;if (++clock_calls==fail_clock_call)return -1;t->tv_sec=0;t->tv_nsec=++tick;return 0;}
static int capture(FILE *f,const char *fmt,...) {(void)f;size_t n=strlen(output);va_list a;va_start(a,fmt);int r=vsnprintf(output+n,sizeof(output)-n,fmt,a);va_end(a);assert(r>=0);++nlines;tick+=100;return r;}
static int fail_alloc;
static void *fake_calloc(size_t a,size_t b){return fail_alloc?NULL:calloc(a,b);}
#define clock_gettime fake_clock
#define fprintf capture
''' + pco + '''
#define calloc fake_calloc
''' + pvr + r'''
int main(void) {
 struct pvr_timing_sample sample={0};struct pco_timing_state shader;
 unsetenv("PVR_PIPELINE_TIMING");assert(!pvr_timing_begin(&sample,'g') && tick==1 && nlines==0);
 setenv("PVR_PIPELINE_TIMING","01",1);assert(!pvr_timing_begin(&sample,'g') && tick==1 && nlines==0);
 setenv("PVR_PIPELINE_TIMING","1",1);assert(pvr_timing_begin(&sample,'g'));
 assert(nlines==2 && sample.scope && sample.tid && sample.id==256);
 uint64_t begin=sample.start;assert(begin>200);
 for(unsigned i=0;i<5;i++) {
  bool active=pco_timing_begin(&shader);assert(active==(i<4));
  if(active) {uint64_t t=pco_timing_now();pco_timing_record("sample_pass",t);
   pco_timing_record("sample_pass",t);pco_timing_finish(&shader);}
 }
 assert(nlines==2 && sample.scope->used==4 && sample.scope->dropped==1);
 assert(sample.scope->shaders[0].entries[0].calls==2);
 unsigned ignored=0;assert(!pco_timing_claim('x', &ignored));
 struct pvr_timing_sample child={0};assert(pvr_timing_begin(&child,'c') && child.id==0);
 assert(pco_timing_begin(&shader));uint64_t ct=pco_timing_now();pco_timing_record("child_pass",ct);pco_timing_finish(&shader);
 pvr_timing_end(&child,0,'c');assert(nlines==2 && pco_timing_scope_current==sample.scope);
 for(int i=0;i<63;i++)assert(!pco_timing_claim('c', &ignored));
 fail_clock_call=clock_calls+2;struct pvr_timing_sample bad={0};assert(!pvr_timing_begin(&bad,'c'));
 assert(nlines==2 && sample.scope->deferred_used==2);
 pvr_timing_end(&sample,-7,'g');assert(pco_timing_scope_current==NULL && !pco_timing_defer_root);
 assert(strstr(output,"dpre") && strstr(output,"child_pass") && strstr(output,"clock_error_start"));
 assert(strstr(output,"pvr_cache=not_queried"));assert(strstr(output,"drop1"));
 assert(strstr(output,"sample_pass"));assert(strstr(output," t"));
 assert(nlines==28); /* root records, deferred child records and start-error records */
 pco_timing_sequence[1]=0;
 fail_alloc=1;assert(pvr_timing_begin(&sample,'g') && !sample.scope);
 pvr_timing_end(&sample,0,'g');assert(strstr(output,"allocation_failed"));
 fail_alloc=0;pco_timing_sequence[0]=pco_timing_sequence[1]=0;fail_clock_call=0;assert(pvr_timing_begin(&sample,'g'));
 assert(pco_timing_begin(&shader));sample.scope->used=PCO_TIMING_MAX_SHADERS;
 pco_timing_finish(&shader);assert(sample.scope->errors==1);sample.scope->used=0;
 pvr_timing_end(&sample,0,'g');
 pco_timing_sequence[0]=pco_timing_sequence[1]=0;fail_clock_call=clock_calls+2;
 assert(!pvr_timing_begin(&sample,'g'));assert(strstr(output,"clock_error_start"));
 assert(!pco_timing_scope_current && !pco_timing_defer_root);
 pco_timing_sequence[0]=pco_timing_sequence[1]=0;fail_clock_call=0;assert(pvr_timing_begin(&sample,'g'));
 fail_clock_call=clock_calls+1;pvr_timing_end(&sample,0,'g');assert(strstr(output,"clock_error_end"));
 assert(!pco_timing_scope_current && !pco_timing_defer_root);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'test.c';e=Path(tmp)/'test';p.write_text(program)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-pthread','-I',str(root/'src/imagination/pco'),str(p),'-o',str(e)],check=True)
 subprocess.run([str(e)],check=True)
print('PASS: gate, correlated IDs/TID, deferred output, overflow bound, retry and allocation failure')
threaded = r"""#define _POSIX_C_SOURCE 200809L
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>
#include <assert.h>
#include "pco_timing.h"
typedef int VkResult;
""" + pco + pvr + r"""
static void *worker(void *x){(void)x;for(int i=0;i<20;i++){
 struct pvr_timing_sample sample={0};
 if(pvr_timing_begin(&sample,'g')) {struct pco_timing_state shader;
  if(pco_timing_begin(&shader)){uint64_t t=pco_timing_now();pco_timing_record("thread_pass",t);pco_timing_finish(&shader);}
  pvr_timing_end(&sample,0,'g');}
 }return 0;}
int main(void){setenv("PVR_PIPELINE_TIMING","1",1);pthread_t t[16];
 for(int i=0;i<16;i++)assert(!pthread_create(&t[i],0,worker,0));
 for(int i=0;i<16;i++){assert(!pthread_join(t[i],0));}return 0;}
"""
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'test.c';e=Path(tmp)/'test';p.write_text(threaded)
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-I',str(root/'src/imagination/pco'),str(p),'-o',str(e)],check=True)
 out=subprocess.run([str(e)],check=True,capture_output=True,text=True).stderr
 import re
 starts=re.findall(r'PL p([0-9a-f]+) i([0-9a-f]+) t([0-9a-f]+) g pre',out)
 passes=re.findall(r'PCO p([0-9a-f]+) i([0-9a-f]+) k0 thread_pass',out)
 assert len(starts)==2 and {int(x[1],16) for x in starts}=={256,320},out
 assert len(passes)==2 and {(x[0],x[1]) for x in passes}=={(x[0],x[1]) for x in starts},out
 assert all(int(x[2],16)!=0 for x in starts)
print('PASS: independent simultaneous threads preserve pipeline to PCO identities')
