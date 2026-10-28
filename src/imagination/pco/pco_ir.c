/*
 * Copyright © 2024 Imagination Technologies Ltd.
 *
 * SPDX-License-Identifier: MIT
 */

/**
 * \file pco_ir.c
 *
 * \brief PCO IR-specific functions.
 */

#include "pco.h"
#include "pco_internal.h"

#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#ifdef __APPLE__
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <sys/sysctl.h>
#include <sys/time.h>
#endif

/* Sampled diagnostic only. The caller invokes timing through PCO_PASS;
 * nested passes are inclusive, and process-local records never contain IR. */
_Thread_local struct pco_timing_state *pco_timing_current;
static unsigned pco_timing_sequence;

uint64_t pco_timing_now(void)
{
   struct timespec t;
   if (clock_gettime(CLOCK_MONOTONIC, &t) || t.tv_sec < 0) return 0;
   return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

bool pco_timing_begin(struct pco_timing_state *state)
{
   const char *enabled = getenv("PVR_PIPELINE_TIMING");
   if (!enabled || strcmp(enabled, "1") || pco_timing_current) return false;
   unsigned ordinal = __atomic_fetch_add(&pco_timing_sequence, 1, __ATOMIC_RELAXED);
   if (ordinal >= 256 || ordinal % 64) return false;
   memset(state, 0, sizeof(*state));
   state->id = ordinal;
   state->start_ns = pco_timing_now();
   if (!state->start_ns) return false;
   pco_timing_current = state;
   return true;
}

void pco_timing_record(const char *name, uint64_t start)
{
   struct pco_timing_state *state = pco_timing_current;
   uint64_t end = pco_timing_now();
   if (!state || !start || end < start) return;
   unsigned i = 0;
   while (i < state->used && strcmp(name, state->entries[i].name)) ++i;
   if (i == state->used) {
      if (i == 64) return;
      state->entries[i].name = name;
      ++state->used;
   }
   uint64_t delta = end - start;
   if (UINT64_MAX - state->entries[i].elapsed_ns < delta) return;
   state->entries[i].elapsed_ns += delta;
   ++state->entries[i].calls;
}

void pco_timing_log(const char *line)
{
#ifdef __APPLE__
   typedef void (*emit_fn)(const char *);
   emit_fn emit = (emit_fn)dlsym(RTLD_DEFAULT, "native_metal_board_text");
   if (emit) { emit(line); return; }
   /* A Metal bundle may be RTLD_LOCAL: locate its already-loaded image. */
   for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
      const char *path = _dyld_get_image_name(i);
      const char *base = path ? strrchr(path, '/') : NULL;
      if (!base || strcmp(base + 1, "NativePowerVRMetal")) continue;
      void *handle = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
      if (!handle) continue;
      emit = (emit_fn)dlsym(handle, "native_metal_board_text");
      if (emit) emit(line);
      dlclose(handle);
      if (emit) return;
   }
#endif
   fprintf(stderr, "%s\n", line);
}

void pco_timing_log_boot(void)
{
   char line[64];
#ifdef __APPLE__
   struct timeval boot; size_t length = sizeof(boot);
   if (!sysctlbyname("kern.boottime", &boot, &length, NULL, 0) && length == sizeof(boot)) {
      snprintf(line, sizeof(line), "TIM pid=%d boot=%lld", (int)getpid(), (long long)boot.tv_sec);
   } else
#endif
      snprintf(line, sizeof(line), "TIM pid=%d boot=unknown", (int)getpid());
   pco_timing_log(line);
}

void pco_timing_finish(struct pco_timing_state *state)
{
   uint64_t end = pco_timing_now();
   pco_timing_current = NULL;
   if (!end || end < state->start_ns) return;
   char line[64];
   pco_timing_log_boot();
   snprintf(line, sizeof(line), "PCO pid=%d id=%u t=%llu", (int)getpid(), state->id,
            (unsigned long long)state->start_ns);
   pco_timing_log(line);
   for (unsigned i = 0; i < state->used; ++i) {
      int length = snprintf(line, sizeof(line), "PCO p%x i%x %.24s n%x t%llx", (unsigned)getpid(), state->id,
                            state->entries[i].name, state->entries[i].calls,
                            (unsigned long long)state->entries[i].elapsed_ns);
      if (length >= 0 && (size_t)length < sizeof(line)) { pco_timing_log(line); continue; }
      snprintf(line, sizeof(line), "PCN p%x i%x k%x %.24s", (unsigned)getpid(), state->id, i, state->entries[i].name);
      pco_timing_log(line);
      snprintf(line, sizeof(line), "PCV p%x i%x k%x n%x t%llx", (unsigned)getpid(), state->id, i,
               state->entries[i].calls, (unsigned long long)state->entries[i].elapsed_ns);
      pco_timing_log(line);
   }
   snprintf(line, sizeof(line), "PCO p%d i%u end=%llu", (int)getpid(), state->id, (unsigned long long)end);
   pco_timing_log(line);
}

/**
 * \brief Runs passes on a PCO shader.
 *
 * \param[in] ctx PCO compiler context.
 * \param[in,out] shader PCO shader.
 */
void pco_process_ir(pco_ctx *ctx, pco_shader *shader)
{
   struct pco_timing_state timing;
   bool timing_active = pco_timing_begin(&timing);
   pco_validate_shader(shader, "before passes");

   PCO_PASS(_, shader, pco_const_imms);
   PCO_PASS(_, shader, pco_opt);

   bool progress;
   do {
      progress = false;
      PCO_PASS(progress, shader, pco_dce);
   } while (progress);

   PCO_PASS(_, shader, pco_bool);
   PCO_PASS(_, shader, pco_cf);

   PCO_PASS(_, shader, pco_shrink_vecs);

   PCO_PASS(_, shader, pco_const_imms);
   PCO_PASS(_, shader, pco_opt_comp_only_vecs);
   PCO_PASS(_, shader, pco_opt);

   do {
      progress = false;
      PCO_PASS(progress, shader, pco_dce);
   } while (progress);

   /* TODO: schedule after RA instead as e.g. vecs may no longer be the first
    * time a drc result is used.
    */
   PCO_PASS(_, shader, pco_schedule);
   PCO_PASS(_, shader, pco_pre_ra_legalize);
   PCO_PASS(_, shader, pco_ra);
   PCO_PASS(_, shader, pco_post_ra_legalize);
   PCO_PASS(_, shader, pco_end);
   PCO_PASS(_, shader, pco_group_instrs);

   pco_validate_shader(shader, "after passes");

   if (pco_should_print_shader(shader))
      pco_print_shader(shader, stdout, "after passes");
   if (timing_active) pco_timing_finish(&timing);
}
