# LLM SWE-bench-style Patch Smoke Report

- model: `gpt-5.4`
- ready: `True`
- model_call_count: `2`
- model_json_parse_success_count: `2`
- executor_contract_ready: `True`
- instance_count: `2`
- tests_passed_count: `2`
- all_model_patches_tests_passed: `True`
- hydration_safe_count: `2`
- evidence_sound_count: `2`
- patch_equal_to_gold_count: `1`
- mean_patch_line_jaccard: `0.75`

## Instance outcomes

- `executor__calculator-001`: tests_passed=`True`, patch_equal_to_gold=`True`, hydration_safe=`True`
- `executor__parser-002`: tests_passed=`True`, patch_equal_to_gold=`False`, hydration_safe=`True`
