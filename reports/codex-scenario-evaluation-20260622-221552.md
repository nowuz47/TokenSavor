# Codex Usage Scenario Evaluation

Generated at: `2026-06-22T13:15:52.370552+00:00`
Model: `gpt-5.4-mini`
Tokenizer status: `heuristic_directional`
Tokenizer note: tiktoken is unavailable in this environment, so counts use heuristic-v1 and should not be treated as billing-grade.

## Summary

- Total scenarios: 80
- Token-saving cases: 15
- Task-optimization cases: 0
- Pass with prompt overhead: 65
- Preservation pass rate: 100.0%
- Average prompt savings rate: 15.6%
- Total original tokens: 79,682
- Total optimized tokens: 15,073
- Total saved tokens: 69,443
- Total overhead tokens: 4,834
- Estimated work savings: 12 minutes
- Tokenizer confidence: `{'heuristic_fallback': 80}`

## Category Summary

| Category | Total | Actual kinds | Avg savings | Avg overhead | Work saved min | Preservation |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| coding | 10 | `{'pass_overhead': 10}` | 0.0% | 69.1 | 0 | 100.0% |
| data | 10 | `{'token_saving': 2, 'pass_overhead': 8}` | 12.9% | 70.0 | 0 | 100.0% |
| debugging | 10 | `{'pass_overhead': 8, 'token_saving': 2}` | 13.2% | 59.3 | 0 | 100.0% |
| docs_planning | 10 | `{'pass_overhead': 10}` | 0.0% | 73.5 | 0 | 100.0% |
| logs | 10 | `{'token_saving': 10}` | 94.7% | 0.0 | 12 | 100.0% |
| refactor | 10 | `{'pass_overhead': 10}` | 0.0% | 69.4 | 0 | 100.0% |
| review_security | 10 | `{'token_saving': 1, 'pass_overhead': 9}` | 3.9% | 73.7 | 0 | 100.0% |
| testing | 10 | `{'pass_overhead': 10}` | 0.0% | 68.4 | 0 | 100.0% |

## Recommendations

- Most Codex-style prompts are short or workflow-oriented. Treat token savings as a subset, not the main success metric.
- Do not auto-rewrite short prompts. Offer task optimization as an explicit work-plan mode or paste only when the user accepts.
- Install/use a model tokenizer or provider count endpoint. heuristic-v1 is useful for direction, but not billing-grade.
- Prioritize logs, stack traces, diffs, CSV, and JSON attachments because they show real input-token reduction.
- Add a context hygiene feature for AGENTS.md, CLAUDE.md, GEMINI.md, and Cursor rules. Always-on instructions are a better savings target than short chat prompts.
- Highest overhead cases should be pass-by-default or plan-only: data_63_sql_retention, data_68_monthly_cost, data_69_team_aggregate, data_70_token_error, data_64_outlier.

## Scenario Results

| ID | Category | Expected | Actual | Original | Optimized | Saved | Overhead | Reason |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| coding_01_calculator_app | coding | task_optimization | pass_overhead | 30 | 99 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_02_crud_api | coding | task_optimization | pass_overhead | 24 | 93 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_03_react_filter_sort | coding | task_optimization | pass_overhead | 23 | 92 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_04_function_option | coding | task_optimization | pass_overhead | 22 | 92 | 0 | 70 | short prompt; rewriting would likely increase tokens |
| coding_05_cli_command | coding | task_optimization | pass_overhead | 24 | 93 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_06_auth_middleware | coding | task_optimization | pass_overhead | 20 | 89 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_07_file_upload | coding | task_optimization | pass_overhead | 24 | 93 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_08_csv_import | coding | task_optimization | pass_overhead | 22 | 91 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_09_batch_job | coding | task_optimization | pass_overhead | 23 | 92 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| coding_10_feature_flag | coding | task_optimization | pass_overhead | 20 | 89 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| debug_11_pytest_failure | debugging | task_optimization | pass_overhead | 26 | 101 | 0 | 75 | short prompt; rewriting would likely increase tokens |
| debug_12_python_stacktrace | debugging | token_saving | token_saving | 1768 | 1137 | 631 | 0 | input tokens reduced |
| debug_13_typescript_build | debugging | token_saving | token_saving | 2606 | 104 | 2502 | 0 | input tokens reduced |
| debug_14_sqlite_migration | debugging | task_optimization | pass_overhead | 23 | 97 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_15_port_conflict | debugging | task_optimization | pass_overhead | 24 | 98 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_16_tray_close | debugging | task_optimization | pass_overhead | 27 | 101 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_17_button_failure | debugging | task_optimization | pass_overhead | 29 | 103 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_18_api_500 | debugging | task_optimization | pass_overhead | 23 | 97 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_19_race_condition | debugging | task_optimization | pass_overhead | 25 | 99 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| debug_20_repro_steps | debugging | task_optimization | pass_overhead | 20 | 94 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| logs_21_cloudwatch_repeat | logs | token_saving | token_saving | 7425 | 1356 | 6069 | 0 | input tokens reduced |
| logs_22_error_1000 | logs | token_saving | token_saving | 15011 | 101 | 14910 | 0 | input tokens reduced |
| logs_23_mixed_frequency | logs | token_saving | token_saving | 2763 | 153 | 2610 | 0 | input tokens reduced |
| logs_24_k8s_restart | logs | token_saving | token_saving | 4188 | 194 | 3994 | 0 | input tokens reduced |
| logs_25_nginx_spike | logs | token_saving | token_saving | 8406 | 1179 | 7227 | 0 | input tokens reduced |
| logs_26_payment_timeout | logs | token_saving | token_saving | 5258 | 101 | 5157 | 0 | input tokens reduced |
| logs_27_auth_failure | logs | token_saving | token_saving | 4887 | 98 | 4789 | 0 | input tokens reduced |
| logs_28_post_deploy | logs | token_saving | token_saving | 4430 | 102 | 4328 | 0 | input tokens reduced |
| logs_29_slow_query | logs | token_saving | token_saving | 4554 | 97 | 4457 | 0 | input tokens reduced |
| logs_30_retry_storm | logs | token_saving | token_saving | 5990 | 95 | 5895 | 0 | input tokens reduced |
| refactor_31_mass_rename | refactor | task_optimization | pass_overhead | 24 | 93 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| refactor_32_legacy_class | refactor | task_optimization | pass_overhead | 21 | 90 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| refactor_33_js_to_ts | refactor | task_optimization | pass_overhead | 20 | 89 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| refactor_34_router_split | refactor | task_optimization | pass_overhead | 20 | 89 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| refactor_35_react_state | refactor | task_optimization | pass_overhead | 16 | 86 | 0 | 70 | short prompt; rewriting would likely increase tokens |
| refactor_36_util_dedupe | refactor | task_optimization | pass_overhead | 17 | 87 | 0 | 70 | short prompt; rewriting would likely increase tokens |
| refactor_37_deprecated_api | refactor | task_optimization | pass_overhead | 17 | 87 | 0 | 70 | short prompt; rewriting would likely increase tokens |
| refactor_38_db_migration | refactor | task_optimization | pass_overhead | 20 | 90 | 0 | 70 | short prompt; rewriting would likely increase tokens |
| refactor_39_module_split | refactor | task_optimization | pass_overhead | 22 | 91 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| refactor_40_config_change | refactor | task_optimization | pass_overhead | 20 | 89 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| test_41_pytest | testing | task_optimization | pass_overhead | 19 | 87 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| test_42_react_testing | testing | task_optimization | pass_overhead | 22 | 90 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| test_43_playwright_smoke | testing | task_optimization | pass_overhead | 24 | 92 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| test_44_regression | testing | task_optimization | pass_overhead | 19 | 88 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| test_45_edge_checklist | testing | task_optimization | pass_overhead | 19 | 87 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| test_46_failing_first | testing | task_optimization | pass_overhead | 21 | 89 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| test_47_snapshot_cleanup | testing | task_optimization | pass_overhead | 19 | 88 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| test_48_contract | testing | task_optimization | pass_overhead | 18 | 87 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| test_49_fixture | testing | task_optimization | pass_overhead | 18 | 87 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| test_50_installer_matrix | testing | task_optimization | pass_overhead | 22 | 90 | 0 | 68 | short prompt; rewriting would likely increase tokens |
| review_51_pr_diff | review_security | token_saving | token_saving | 902 | 549 | 353 | 0 | input tokens reduced |
| review_52_sql_injection | review_security | task_optimization | pass_overhead | 21 | 103 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_53_secret_exposure | review_security | task_optimization | pass_overhead | 20 | 102 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_54_eval | review_security | task_optimization | pass_overhead | 18 | 100 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_55_auth_bypass | review_security | task_optimization | pass_overhead | 17 | 99 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_56_permission_scope | review_security | task_optimization | pass_overhead | 23 | 105 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_57_dependency | review_security | task_optimization | pass_overhead | 21 | 103 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_58_error_handling | review_security | task_optimization | pass_overhead | 22 | 103 | 0 | 81 | short prompt; rewriting would likely increase tokens |
| review_59_privacy_logging | review_security | task_optimization | pass_overhead | 19 | 101 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| review_60_installer_trust | review_security | task_optimization | pass_overhead | 21 | 103 | 0 | 82 | short prompt; rewriting would likely increase tokens |
| data_61_csv_sales | data | token_saving | token_saving | 5061 | 1736 | 3325 | 0 | input tokens reduced |
| data_62_json_schema | data | token_saving | token_saving | 5051 | 1855 | 3196 | 0 | input tokens reduced |
| data_63_sql_retention | data | task_optimization | pass_overhead | 21 | 109 | 0 | 88 | short prompt; rewriting would likely increase tokens |
| data_64_outlier | data | task_optimization | pass_overhead | 21 | 108 | 0 | 87 | short prompt; rewriting would likely increase tokens |
| data_65_funnel | data | task_optimization | pass_overhead | 22 | 109 | 0 | 87 | short prompt; rewriting would likely increase tokens |
| data_66_ab_test | data | task_optimization | pass_overhead | 22 | 109 | 0 | 87 | short prompt; rewriting would likely increase tokens |
| data_67_dashboard_metrics | data | task_optimization | pass_overhead | 22 | 109 | 0 | 87 | short prompt; rewriting would likely increase tokens |
| data_68_monthly_cost | data | task_optimization | pass_overhead | 21 | 109 | 0 | 88 | short prompt; rewriting would likely increase tokens |
| data_69_team_aggregate | data | task_optimization | pass_overhead | 16 | 104 | 0 | 88 | short prompt; rewriting would likely increase tokens |
| data_70_token_error | data | task_optimization | pass_overhead | 20 | 108 | 0 | 88 | short prompt; rewriting would likely increase tokens |
| docs_71_architecture | docs_planning | task_optimization | pass_overhead | 20 | 94 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_72_mvp_plan | docs_planning | task_optimization | pass_overhead | 15 | 89 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_73_release_checklist | docs_planning | task_optimization | pass_overhead | 21 | 95 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_74_runbook | docs_planning | task_optimization | pass_overhead | 16 | 90 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_75_onboarding | docs_planning | task_optimization | pass_overhead | 17 | 86 | 0 | 69 | short prompt; rewriting would likely increase tokens |
| docs_76_agents | docs_planning | context_hygiene | pass_overhead | 24 | 98 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_77_memory_files | docs_planning | context_hygiene | pass_overhead | 26 | 100 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_78_cursor_rules | docs_planning | context_hygiene | pass_overhead | 24 | 98 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_79_human_audit | docs_planning | task_optimization | pass_overhead | 21 | 95 | 0 | 74 | short prompt; rewriting would likely increase tokens |
| docs_80_rollout_gate | docs_planning | task_optimization | pass_overhead | 24 | 98 | 0 | 74 | short prompt; rewriting would likely increase tokens |
