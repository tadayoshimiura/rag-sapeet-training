# Aurora Mapping (Test Generation)

This doc maps the question generation output to Aurora tables (Issue #177).

## Input (Aurora -> prompt variables)

- `test_genre` -> `{test_genre}` (comprehension / skill / followup)
- `question_count` -> `{requested_count}`
- `lecture_id` -> `{lecture_id}`
- (optional) `course_id` -> `{course_id}` (not in DB; keep for tracking)
- (optional) classification/meta (if stored in Aurora or API)
  - `{genre_id}`, `{subgenre_id}`, `{tags}`, `{skills_to_learn}`
  - `{course_name}`, `{course_description}`, `{course_difficulty}`
  - `{lecture_title}`, `{lecture_heading}`, `{lecture_description}`, `{lecture_material_type}`
  - `{scene_type}`, `{pass_criteria}`, `{proficiency_rubric}`, `{scene_target_items}`
  - `{num_candidates}`, `{max_adopt}`, `{num_questions_in_exam}`

## Output (LLM -> Aurora tables)

### generated_test_questions

- `question_text` -> `generated_test_questions.question_text`
- `question_type` -> `generated_test_questions.question_type`
- `points` -> `generated_test_questions.points`
- `job_id` -> `generated_test_questions.job_id` (set by job executor)
- `display_order` -> set in app/DB (not output from LLM)
- `is_approved` -> set in app/DB

### generated_test_options

- `options[].option_text` -> `generated_test_options.option_text`
- `options[].is_correct` -> `generated_test_options.is_correct`
- `question_id` -> `generated_test_options.question_id` (set by app/DB)
- `display_order` -> set in app/DB

## Fields not in DB (need decision)

- `explanation` (解説)
- `evidence.chunk_id` / `evidence.quote` (根拠)
- `tags`
- `is_canonical`
- `weight_flag`
- `course_id`

These require either:
- adding columns to Aurora, or
- storing in a side table / JSON blob, or
- keeping only in the vector DB / object storage.

## Proposed minimum (for repo baseline)

Keep Aurora as the source of truth and store the extra fields in a JSON blob
until the schema is extended.

- Add `generated_test_questions.extra_payload` (JSONB)
- Store: explanation, evidence, tags, is_canonical, weight_flag, course_id
- Keep core columns (`question_text`, `question_type`, `points`) as-is

This allows immediate integration without schema churn, and can be migrated
to columns later.

## test_genre mapping (Aurora is source)

- `test_genre = comprehension` -> prompt `test_genre = comprehension`
- `test_genre = skill` -> prompt `test_genre = skill`
- `test_genre = followup` -> prompt `test_genre = followup`
