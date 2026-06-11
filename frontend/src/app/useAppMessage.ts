import { App } from 'antd'
import type { MessageInstance } from 'antd/es/message/interface'
import { ApiError } from '@/api/client'

/** 使用 antd ``App`` 上下文中的 message，避免静态 ``message.*`` 无法消费主题。 */
export function useAppMessage(): MessageInstance {
  return App.useApp().message
}

/** Resolve API error code to a localized message when an i18n key exists. */
export function resolveApiErrorMessage(
  t: (key: string, options?: { defaultValue?: string }) => string,
  e: ApiError,
): string {
  const key = `apiErrors.${e.code}`
  const translated = t(key, { defaultValue: '' })
  return translated.trim() ? translated : e.message
}

/** 将接口/未知错误展示为 message 提示。 */
export function showAppError(
  messageApi: MessageInstance,
  t: (key: string, options?: { defaultValue?: string }) => string,
  e: unknown,
) {
  if (e instanceof ApiError) {
    void messageApi.error(resolveApiErrorMessage(t, e))
    return
  }
  if (e instanceof DOMException && e.name === 'TimeoutError') {
    void messageApi.error(t('common.requestTimeout'))
    return
  }
  void messageApi.error(t('common.error'))
}
