/* SPDX-License-Identifier: MIT */
#ifndef PCO_TIMING_H
#define PCO_TIMING_H
#include <stdbool.h>
#include <stdint.h>

struct pco_timing_entry { const char *name; uint64_t elapsed_ns; unsigned calls; };
struct pco_timing_state { uint64_t start_ns; unsigned id, used; struct pco_timing_entry entries[64]; };
extern _Thread_local struct pco_timing_state *pco_timing_current;
bool pco_timing_begin(struct pco_timing_state *state);
uint64_t pco_timing_now(void);
void pco_timing_record(const char *name, uint64_t start);
void pco_timing_finish(struct pco_timing_state *state);
void pco_timing_log(const char *line);
void pco_timing_log_boot(void);
#endif
