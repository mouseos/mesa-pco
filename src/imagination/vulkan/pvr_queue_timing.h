/* SPDX-License-Identifier: MIT */
#ifndef PVR_QUEUE_TIMING_H
#define PVR_QUEUE_TIMING_H
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "pco/pco_timing.h"

/* Emit after the driver submit callback returns. Each compiled architecture
 * reports at most four slow submits per process; default off. Hexadecimal ns.
 * If the winsys uses threaded submission this is worker, not caller, time. */
struct pvr_queue_timing { uint64_t stamp[5]; unsigned phase; bool enabled; };
static unsigned pvr_queue_timing_reports;
static inline void pvr_queue_timing_begin(struct pvr_queue_timing *t)
{
   const char *flag = getenv("PVR_QUEUE_TIMING");
   t->enabled = flag && !strcmp(flag, "1") &&
      __atomic_load_n(&pvr_queue_timing_reports, __ATOMIC_RELAXED) < 4;
   if (t->enabled) t->stamp[0] = pco_timing_now();
}
static inline void pvr_queue_timing_step(struct pvr_queue_timing *t, unsigned phase)
{
   if (!t->enabled || phase > 4) return;
   t->stamp[phase] = pco_timing_now();
   t->phase = phase;
}
static inline void pvr_queue_timing_end(struct pvr_queue_timing *t, int result)
{
   if (!t->enabled) return;
   const uint64_t end = pco_timing_now();
   bool valid = t->stamp[0] && end >= t->stamp[0];
   for (unsigned i=1; i<=t->phase; i++)
      valid = valid && t->stamp[i] >= t->stamp[i-1] && t->stamp[i] <= end;
   if (valid && end - t->stamp[0] < UINT64_C(1000000000)) return;
   unsigned id = __atomic_load_n(&pvr_queue_timing_reports, __ATOMIC_RELAXED);
   do { if (id >= 4) return; }
   while (!__atomic_compare_exchange_n(&pvr_queue_timing_reports, &id, id+1,
                                        false, __ATOMIC_RELAXED, __ATOMIC_RELAXED));
   char line[64];
   snprintf(line,sizeof(line),"QT p%x i%x t%llx ph%x r%x",(unsigned)getpid(),id,
            (unsigned long long)pco_timing_tid(),t->phase,(unsigned)result);
   pco_timing_log(line);
   if (!valid) {
      snprintf(line,sizeof(line),"QT p%x i%x clock_error",(unsigned)getpid(),id);
      pco_timing_log(line);
      return;
   }
   snprintf(line,sizeof(line),"QT p%x i%x begin%llx",(unsigned)getpid(),id,
            (unsigned long long)t->stamp[0]);
   pco_timing_log(line);
   snprintf(line,sizeof(line),"QT p%x i%x end%llx",(unsigned)getpid(),id,
            (unsigned long long)end);
   pco_timing_log(line);
   for (unsigned i=1; i<=t->phase; i++) {
      snprintf(line,sizeof(line),"QT p%x i%x s%x n%llx",(unsigned)getpid(),id,i,
               (unsigned long long)(t->stamp[i]-t->stamp[i-1]));
      pco_timing_log(line);
   }
   snprintf(line,sizeof(line),"QT p%x i%x total%llx",(unsigned)getpid(),id,
            (unsigned long long)(end-t->stamp[0]));
   pco_timing_log(line);
}
#endif
