/* SPDX-License-Identifier: MIT */
#ifndef PCO_TIMING_H
#define PCO_TIMING_H
#include <stdbool.h>
#include <stdint.h>

#define PCO_TIMING_MAX_SHADERS 4u
#define PCO_TIMING_MAX_PASSES 64u
struct pco_timing_scope;
struct pco_timing_entry { const char *name; uint64_t elapsed_ns; unsigned calls; };
struct pco_timing_state {
   struct pco_timing_scope *scope;
   uint64_t start_ns, end_ns;
   unsigned id, used, errors;
   struct pco_timing_entry entries[PCO_TIMING_MAX_PASSES];
};
struct pco_timing_scope {
   struct pco_timing_scope *previous;
   uint64_t tid;
   unsigned id, attempts, used, dropped, errors;
   struct pco_timing_state shaders[PCO_TIMING_MAX_SHADERS];
};
extern _Thread_local struct pco_timing_state *pco_timing_current;
extern _Thread_local struct pco_timing_scope *pco_timing_scope_current;
bool pco_timing_claim(unsigned *id);
bool pco_timing_begin(struct pco_timing_state *state);
uint64_t pco_timing_now(void);
uint64_t pco_timing_tid(void);
void pco_timing_record(const char *name, uint64_t start);
void pco_timing_finish(struct pco_timing_state *state);
void pco_timing_scope_report(const struct pco_timing_scope *scope);
void pco_timing_log(const char *line);
void pco_timing_log_boot(void);
#endif
