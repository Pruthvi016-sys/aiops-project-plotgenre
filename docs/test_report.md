# Test report

Generated 2026-11-14 11:37 UTC on Linux-7.0.0-29-generic-x86_64-with-glibc2.43 (Python 3.12.16) by `scripts/generate_test_report.py`.

## Summary

| Total | Passed | Failed | Skipped | Line coverage |
|---|---|---|---|---|
| 86 | 86 | 0 | 0 | 70.8% |

## Acceptance criteria (see docs/test_plan.md)

| Criterion | Target | Measured | Result |
|---|---|---|---|
| AC-1 Test micro-F1 | >= 0.40 | 0.6639 | PASS |
| AC-2 p95 single-prediction latency (model) | < 500 ms | 16.9 ms | PASS |
| AC-3 All planned test cases pass | 0 failures | 0 failures | PASS |

## Test cases

| Level | Module | Test | Result | Time (s) |
|---|---|---|---|---|
| e2e | test_stack | `test_ui_is_served` | passed | 0.01 |
| e2e | test_stack | `test_predict_through_ui_proxy` | passed | 0.10 |
| e2e | test_stack | `test_gateway_enforces_api_key` | passed | 0.02 |
| e2e | test_stack | `test_p95_latency_under_500ms` | passed | 1.51 |
| e2e | test_stack | `test_model_info_matches_registry` | passed | 0.00 |
| e2e | test_stack | `test_pipeline_console_endpoints` | passed | 0.04 |
| e2e | test_stack | `test_metrics_exposed` | passed | 0.02 |
| e2e | test_stack | `test_acceptance_criteria_report` | passed | 0.00 |
| e2e | test_stack | `test_browser_flow` | passed | 4.09 |
| integration | test_frontend | `test_index_and_static` | passed | 0.05 |
| integration | test_frontend | `test_config_exposes_no_secret` | passed | 0.01 |
| integration | test_frontend | `test_proxy_adds_key_and_respects_allow_list` | passed | 0.02 |
| integration | test_frontend | `test_backend_unreachable` | passed | 0.01 |
| integration | test_frontend | `test_telemetry_metrics` | passed | 0.03 |
| integration | test_gateway_api | `test_health_needs_no_auth` | passed | 0.03 |
| integration | test_gateway_api | `test_ready_reflects_model_server` | passed | 0.06 |
| integration | test_gateway_api | `test_predict_requires_api_key` | passed | 0.03 |
| integration | test_gateway_api | `test_predict_success_contract` | passed | 0.04 |
| integration | test_gateway_api | `test_predict_validation[payload0-text_too_short]` | passed | 0.03 |
| integration | test_gateway_api | `test_predict_validation[payload1-empty_text]` | passed | 0.03 |
| integration | test_gateway_api | `test_predict_validation[payload2-invalid_input]` | passed | 0.03 |
| integration | test_gateway_api | `test_predict_validation[payload3-invalid_input]` | passed | 0.03 |
| integration | test_gateway_api | `test_short_text_warning` | passed | 0.03 |
| integration | test_gateway_api | `test_model_server_down_gives_503` | passed | 0.94 |
| integration | test_gateway_api | `test_model_server_error_gives_502` | passed | 0.04 |
| integration | test_gateway_api | `test_batch` | passed | 0.04 |
| integration | test_gateway_api | `test_model_info_and_genres` | passed | 0.04 |
| integration | test_gateway_api | `test_metrics_and_live_drift` | passed | 0.17 |
| integration | test_model_and_data | `test_pyfunc_loads_encrypted_model_and_predicts` | passed | 0.14 |
| integration | test_model_and_data | `test_ray_preprocess_pipeline` | passed | 4.52 |
| integration | test_model_and_data | `test_ray_parallel_transform_matches_sequential` | passed | 0.93 |
| integration | test_model_and_data | `test_quality_gate_rejects_bad_data` | passed | 1.12 |
| integration | test_pipeline_runner | `test_dag_matches_dvc_yaml` | passed | 0.07 |
| integration | test_pipeline_runner | `test_runs_groups_terminal_runs` | passed | 0.01 |
| integration | test_pipeline_runner | `test_status_and_reports` | passed | 0.05 |
| integration | test_pipeline_runner | `test_trigger_requires_key_and_starts` | passed | 0.02 |
| integration | test_pipeline_runner | `test_alert_webhook` | passed | 0.02 |
| integration | test_pipeline_runner | `test_set_data_version_preserves_comments` | passed | 0.02 |
| integration | test_pipeline_runner | `test_log_endpoint_validation` | passed | 0.02 |
| unit | test_cleaning | `test_clean_text_strips_markup_urls_refs_and_whitespace` | passed | 0.00 |
| unit | test_cleaning | `test_clean_text_empty[None]` | passed | 0.00 |
| unit | test_cleaning | `test_clean_text_empty[]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[1999-1999]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[1999-05-21-1999]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[2010-03-2010]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[-None]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[None-None]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_year[May 1999-None]` | passed | 0.00 |
| unit | test_cleaning | `test_parse_freebase_genres_valid_and_invalid` | passed | 0.00 |
| unit | test_cleaning | `test_map_genres_multi_label_and_dedup` | passed | 0.00 |
| unit | test_cleaning | `test_word_count` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[empty_text]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[too_short]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[missing_year]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[year_out_of_range]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[no_target_genre]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[too_long]` | passed | 0.00 |
| unit | test_cleaning | `test_validate_record[valid]` | passed | 0.00 |
| unit | test_crypto | `test_roundtrip` | passed | 0.00 |
| unit | test_crypto | `test_wrong_key_is_rejected` | passed | 0.00 |
| unit | test_crypto | `test_tampered_file_is_rejected` | passed | 0.00 |
| unit | test_crypto | `test_missing_or_invalid_key` | passed | 0.00 |
| unit | test_drift_core | `test_tokenize_lowercases_and_drops_stopwords_and_short_tokens` | passed | 0.00 |
| unit | test_drift_core | `test_js_distance_bounds` | passed | 0.01 |
| unit | test_drift_core | `test_js_distance_rejects_bad_input` | passed | 0.00 |
| unit | test_drift_core | `test_term_drift_detects_shift` | passed | 0.01 |
| unit | test_drift_core | `test_term_drift_empty_current_is_zero` | passed | 0.00 |
| unit | test_drift_core | `test_label_drift` | passed | 0.00 |
| unit | test_explain_and_tracker | `test_extract_weights_shapes[base0]` | passed | 0.19 |
| unit | test_explain_and_tracker | `test_extract_weights_shapes[base1]` | passed | 0.20 |
| unit | test_explain_and_tracker | `test_extract_weights_rejects_unfitted` | passed | 0.00 |
| unit | test_explain_and_tracker | `test_explain_row_returns_relevant_words` | passed | 0.00 |
| unit | test_explain_and_tracker | `test_track_stage_records_success_and_failure` | passed | 0.01 |
| unit | test_explain_and_tracker | `test_genre_model_always_predicts_one_label` | passed | 0.01 |
| unit | test_split_and_train_helpers | `test_select_version` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_make_splits_sizes_and_disjoint` | passed | 0.05 |
| unit | test_split_and_train_helpers | `test_make_splits_is_reproducible` | passed | 0.03 |
| unit | test_split_and_train_helpers | `test_apply_threshold_never_returns_empty_rows` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_tune_threshold_picks_best` | passed | 0.01 |
| unit | test_split_and_train_helpers | `test_multilabel_metrics_perfect` | passed | 0.01 |
| unit | test_split_and_train_helpers | `test_build_candidate_unknown` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_decide_promotion[0.3-None-False]` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_decide_promotion[0.6-None-True]` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_decide_promotion[0.6-0.65-False]` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_decide_promotion[0.65-0.65-True]` | passed | 0.00 |
| unit | test_split_and_train_helpers | `test_decide_promotion[0.7-0.65-True]` | passed | 0.00 |
