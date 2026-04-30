/** Declares API data contracts for the workspace celery jobs list page. */

/** One celery job row returned by list/detail endpoints. */
export type CeleryJob = {
  id: string
  workspace_id: string
  name: string
  task_code: string
  task: string
  cron: string | null
  args_json: Record<string, unknown> | unknown[] | null
  kwargs_json: Record<string, unknown> | null
  timezone: string | null
  enabled: boolean
  next_run_at: string | null
  last_run_at: string | null
  last_status: string | null
  last_error: string | null
  version: number
  status: string | null
  remark: string | null
  create_at: string | null
  update_at: string | null
}

/** Standard page payload for celery job list endpoint. */
export type CeleryJobListPage = {
  items: CeleryJob[]
  total: number
}

/** Query params used by list endpoint. */
export type CeleryJobListParams = {
  page?: number
  page_size?: number
  name?: string
  task_code?: string
  task?: string
  enabled?: boolean
}

/** Payload for creating one celery job row. */
export type CeleryJobCreateBody = {
  name: string
  task_code: string
  task: string
  cron?: string | null
  args_json?: Record<string, unknown> | unknown[] | null
  kwargs_json?: Record<string, unknown> | null
  timezone?: string | null
  enabled?: boolean
  status?: string | null
  remark?: string | null
}

/** Partial payload for updating a celery job. */
export type CeleryJobPatchBody = {
  name?: string | null
  task_code?: string | null
  task?: string | null
  cron?: string | null
  args_json?: Record<string, unknown> | unknown[] | null
  kwargs_json?: Record<string, unknown> | null
  timezone?: string | null
  enabled?: boolean | null
  status?: string | null
  remark?: string | null
}

/** Run-now response payload with accepted task id. */
export type CeleryJobRunNowOut = {
  accepted: boolean
  job_id: string
  task_id: string
}
