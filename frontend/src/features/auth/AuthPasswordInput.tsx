import { Input } from 'antd'
import type { ComponentProps } from 'react'

export type AuthPasswordInputProps = ComponentProps<typeof Input.Password>

/**
 * 登录/注册密码框：标准掩码密码输入（含可见性切换），统一自动完成与样式。
 */
export function AuthPasswordInput({
  autoComplete = 'current-password',
  ...props
}: AuthPasswordInputProps) {
  return <Input.Password {...props} autoComplete={autoComplete} />
}
