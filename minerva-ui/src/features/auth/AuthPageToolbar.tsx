import type { AuthTone } from '@/features/auth/authTheme'
import { MinervaLangThemeControls } from '@/features/auth/MinervaLangThemeControls'

type Props = {
  tone: AuthTone
  onToneChange: (t: AuthTone) => void
}

export function AuthPageToolbar({ tone, onToneChange }: Props) {
  return (
    <div className="auth-page-toolbar">
      <MinervaLangThemeControls tone={tone} onToneChange={onToneChange} />
    </div>
  )
}
