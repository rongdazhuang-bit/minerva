import { App } from 'antd'
import type { MessageInstance } from 'antd/es/message/interface'
import { ApiError } from '@/api/client'

/** 使用 antd ``App`` 上下文中的 message，避免静态 ``message.*`` 无法消费主题。 */
export function useAppMessage(): MessageInstance {
  return App.useApp().message
}

/** 将接口/未知错误展示为 message 提示。 */
export function showAppError(
  messageApi: MessageInstance,
  t: (key: string) => string,
  e: unknown,
) {
  if (e instanceof ApiError) {
    void messageApi.error(e.message)
    return
  }
  if (e instanceof DOMException && e.name === 'TimeoutError') {
    void messageApi.error(t('common.requestTimeout'))
    return
  }
  void messageApi.error(t('common.error'))
}
