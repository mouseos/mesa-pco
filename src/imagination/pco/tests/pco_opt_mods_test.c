/* SPDX-License-Identifier: MIT */
#include "pco_internal.h"
#include "pco_builder.h"
#include "util/u_dynarray.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int alloc_fail;
static int grow_fail;
static unsigned failed_injections, grow_calls;
static void *test_index_alloc(void *ctx, size_t size, unsigned count)
{
   if (alloc_fail && !ctx && size == sizeof(struct util_dynarray)) {
      ++failed_injections;
      return NULL;
   }
   return rzalloc_array_size(ctx, size, count);
}
static void *test_index_grow(struct util_dynarray *buf, size_t size)
{
   if (grow_fail && ++grow_calls == (unsigned)grow_fail) {
      ++failed_injections;
      return NULL;
   }
   return util_dynarray_grow_bytes(buf, 1, size);
}
#undef rzalloc_array_size
#define rzalloc_array_size(ctx, size, count) test_index_alloc(ctx, size, count)
#undef util_dynarray_grow
#define util_dynarray_grow(buf, type, count) test_index_grow(buf, sizeof(type))
#ifndef PCO_OPT_SOURCE
#define PCO_OPT_SOURCE "../pco_opt.c"
#endif
#include PCO_OPT_SOURCE
#ifdef NDEBUG
#error PCO validation requires assertions enabled
#endif
#include "../pco_validate.c"

static pco_instr *emit(pco_func *f, pco_block *b, enum pco_op op,
                       unsigned dst, unsigned a, unsigned c, unsigned n)
{
   pco_instr *i = pco_instr_create(f, 1, n);
   i->op = op;
   i->parent_block = b;
   i->dest[0] = pco_ref_ssa(dst, 32, 1);
   i->src[0] = pco_ref_ssa(a, 32, 1);
   if (n == 2)
      i->src[1] = pco_ref_ssa(c, 32, 1);
   list_addtail(&i->link, &b->instrs);
   return i;
}

int main(int argc, char **argv)
{
   setvbuf(stdout, NULL, _IONBF, 0);
   alloc_fail = argc > 1 && !strcmp(argv[1], "alloc");
   grow_fail = argc > 1 && !strcmp(argv[1], "grow") ? 1 :
               argc > 1 && !strcmp(argv[1], "grow2") ? 2 : 0;
   pco_shader *shader = rzalloc(NULL, pco_shader);
   list_inithead(&shader->funcs);
   pco_func *f = pco_func_create(shader, PCO_FUNC_TYPE_ENTRYPOINT, 0);
   pco_block *b1 = pco_block_create(f), *b2 = pco_block_create(f);
   b1->cf_node.parent = b2->cf_node.parent = &f->cf_node;
   b1->cf_node.flag = b2->cf_node.flag = PCO_CF_NODE_FLAG_BODY;
   list_addtail(&b1->cf_node.link, &f->body);
   list_addtail(&b2->cf_node.link, &f->body);
   f->next_ssa = 100;
   if (!(argc > 1 && !strcmp(argv[1], "invalid"))) {
      pco_instr *input = emit(f,b1,PCO_OP_MOV,0,0,0,1);
      input->src[0] = pco_ref_imm32(0);
   }
   emit(f,b1,PCO_OP_FNEG,1,0,0,1);
   emit(f,b1,PCO_OP_FABS,2,0,0,1);
   emit(f,b1,PCO_OP_FFLR,3,0,0,1);
   emit(f,b1,PCO_OP_FNEG,4,0,0,1);
   emit(f,b1,PCO_OP_FADD,5,1,2,2);
   emit(f,b1,PCO_OP_FADD,6,1,1,2);
   emit(f,b2,PCO_OP_FMUL,7,3,1,2);
   emit(f,b2,PCO_OP_FADD,8,2,3,2);
   emit(f,b2,PCO_OP_FNEG,9,0,0,1);
   struct pco_opt_ctx ctx = { .mem_ctx = ralloc_context(NULL) };
   pco_validate_shader(shader, "before prep");
   bool progress = pco_opt_prep_mods(shader, &ctx);
   pco_validate_shader(shader, "after prep");
   if ((alloc_fail || grow_fail) && !failed_injections)
      return 2;
   printf("progress=%d\n", progress);
   pco_foreach_instr_in_func (i, f) {
      printf("%u %u %u", i->op, i->num_dests, i->num_srcs);
      for (unsigned n = 0; n < i->num_dests; ++n) {
         uint64_t bits; memcpy(&bits, &i->dest[n], sizeof(bits));
         printf(" %016llx", (unsigned long long)bits);
      }
      for (unsigned n = 0; n < i->num_srcs; ++n) {
         uint64_t bits; memcpy(&bits, &i->src[n], sizeof(bits));
         printf(" %016llx", (unsigned long long)bits);
      }
      puts("");
   }
   ralloc_free(ctx.mem_ctx);
   ralloc_free(shader);
   return 0;
}
