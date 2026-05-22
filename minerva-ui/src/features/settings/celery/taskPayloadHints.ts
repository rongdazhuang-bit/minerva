/** Known Celery task names and create-form default payloads for the scheduler UI. */

/** Document translation worker task (must pass an existing ``doc_translate_job.id``). */
export const DOC_TRANSLATE_RUN_TASK_NAME = 'translate.run_job'

/** Demo noop task used in scheduler examples. */
export const DEMO_DEFAULT_JOB_TASK_NAME = 'demo.default_job'

/** Default positional-args JSON for ``demo.default_job``. */
export const DEMO_DEFAULT_ARGS_JSON = JSON.stringify(['minerva'], null, 2)

/** Default keyword-args JSON for scheduled demo / audit kwargs. */
export const DEMO_DEFAULT_KWARGS_JSON = JSON.stringify({ source: 'scheduler' }, null, 2)

/** Empty args for ``translate.run_job`` (operator must paste a real job UUID). */
export const TRANSLATE_RUN_JOB_ARGS_JSON = '[]'

/** Example kwargs when job_id is passed by name instead of positionally. */
export const TRANSLATE_RUN_JOB_KWARGS_JSON_EXAMPLE = JSON.stringify(
  { job_id: '550e8400-e29b-41d4-a716-446655440000', source: 'scheduler' },
  null,
  2,
)

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** Returns true when ``value`` is a canonical UUID string. */
export function isUuidString(value: string): boolean {
  return UUID_RE.test(value.trim())
}

/** Extract raw job id string from parsed args/kwargs (before UUID validation). */
export function rawTranslateRunJobId(
  args: unknown,
  kwargs: unknown,
): string | null {
  if (Array.isArray(args) && args.length > 0) {
    const first = args[0]
    if (first != null && String(first).trim() !== '') {
      return String(first).trim()
    }
  }
  if (kwargs != null && typeof kwargs === 'object' && !Array.isArray(kwargs)) {
    const raw = (kwargs as Record<string, unknown>).job_id
    if (raw != null && String(raw).trim() !== '') {
      return String(raw).trim()
    }
  }
  return null
}

/** Default args/kwargs textarea values for the create drawer from task name. */
export function defaultPayloadJsonForTask(taskName: string): {
  args_json: string
  kwargs_json: string
} {
  const task = taskName.trim()
  if (task === DOC_TRANSLATE_RUN_TASK_NAME) {
    return {
      args_json: TRANSLATE_RUN_JOB_ARGS_JSON,
      kwargs_json: TRANSLATE_RUN_JOB_KWARGS_JSON_EXAMPLE,
    }
  }
  return {
    args_json: DEMO_DEFAULT_ARGS_JSON,
    kwargs_json: DEMO_DEFAULT_KWARGS_JSON,
  }
}
