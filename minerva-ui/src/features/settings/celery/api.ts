/** Wraps workspace-scoped celery job APIs used by settings list page. */

import { apiJson } from '@/api/client'
import type {
  CeleryJob,
  CeleryJobListPage,
  CeleryJobListParams,
  CeleryJobPatchBody,
  CeleryJobRunNowOut,
} from './types'

/** Builds the celery jobs API path under one workspace. */
function celeryJobsPath(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/celery-jobs${suffix}`
}

/** Fetches one page of celery jobs with optional filters. */
export function listCeleryJobs(workspaceId: string, params?: CeleryJobListParams) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  if (params?.name != null && params.name.trim() !== '') sp.set('name', params.name.trim())
  if (params?.task_code != null && params.task_code.trim() !== '') {
    sp.set('task_code', params.task_code.trim())
  }
  if (params?.task != null && params.task.trim() !== '') sp.set('task', params.task.trim())
  if (params?.enabled != null) sp.set('enabled', String(params.enabled))
  const query = sp.toString()
  return apiJson<CeleryJobListPage>(celeryJobsPath(workspaceId, query ? `?${query}` : ''))
}

/** Patches one celery job and returns refreshed detail. */
export function patchCeleryJob(workspaceId: string, jobId: string, body: CeleryJobPatchBody) {
  return apiJson<CeleryJob>(celeryJobsPath(workspaceId, `/${jobId}`), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Deletes one celery job row. */
export function deleteCeleryJob(workspaceId: string, jobId: string) {
  return apiJson<null>(celeryJobsPath(workspaceId, `/${jobId}`), {
    method: 'DELETE',
  })
}

/** Sends run-now command for one celery job. */
export function runCeleryJobNow(workspaceId: string, jobId: string) {
  return apiJson<CeleryJobRunNowOut>(celeryJobsPath(workspaceId, `/${jobId}/run-now`), {
    method: 'POST',
  })
}

/** Stops one celery job by setting it disabled on backend. */
export function stopCeleryJob(workspaceId: string, jobId: string) {
  return apiJson<CeleryJob>(celeryJobsPath(workspaceId, `/${jobId}/stop`), {
    method: 'POST',
  })
}

/** Starts one celery job by setting it enabled on backend. */
export function startCeleryJob(workspaceId: string, jobId: string) {
  return apiJson<CeleryJob>(celeryJobsPath(workspaceId, `/${jobId}/start`), {
    method: 'POST',
  })
}
