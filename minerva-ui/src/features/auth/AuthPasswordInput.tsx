import { Input } from 'antd'
import type { InputProps } from 'antd'

export type AuthPasswordInputProps = Omit<InputProps, 'type'>

/**
 * 登录/注册密码框：明文输入（与产品要求一致），保留独立组件便于统一样式与自动填充属性。
 */
export function AuthPasswordInput({
  autoComplete = 'current-password',
  ...props
}: AuthPasswordInputProps) {
  return <Input {...props} type="text" autoComplete={autoComplete} />
}
