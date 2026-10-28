#!/usr/bin/env python3
"""Check the actual pipeline call sites, recursion guard and cache claims."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[4]
s=(root/'src/imagination/vulkan/pvr_arch_pipeline.c').read_text()
for name,kind in [('pvr_compute_pipeline_create','c'),('pvr_graphics_pipeline_create','g')]:
 at=s.index('const VkResult local_result =\n         '+name)
 assert f"pvr_timing_begin(&timing_sample, '{kind}')" in s[at-250:at]
 assert f"pvr_timing_end(&timing_sample, local_result, '{kind}')" in s[at:at+500]
 assert 'if (!timing && outer_scope) pco_timing_scope_current = NULL;' in s[at-300:at]
 assert 'else if (outer_scope) pco_timing_scope_current = outer_scope;' in s[at:at+600]
for name in ('pvr_compute_pipeline_compile','pvr_graphics_pipeline_compile'):
 at=s.index(name+'(');first=s.index('{',at);depth=1;end=first+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 assert not re.search(r'\bcache\b',s[first:end]),name
assert 'pvr_cache=not_queried' in s and 'cache=hit' not in s and 'cache=miss' not in s
assert 'pco_timing_scope_report(d->scope)' in s
assert 'pco_timing_pipeline_depth++' in s and '--pco_timing_pipeline_depth' in s
assert 'pvr_timing_defer(sample->root' in s
print('PASS: both call sites, nested scope restoration, no PVR pipeline cache lookup and deferred report')
