import { Select, Space } from 'antd'
import type { SelectProps } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { MENU_ICON_NAMES, menuIconMap, resolveMenuIcon } from './menuIconMap'
import './MenuIconSelect.css'

type MenuIconSelectProps = {
  value?: string | null
  onChange?: (value: string | null) => void
}

const MENU_ICON_SELECT_POPUP_CLASS_NAMES = {
  popup: { root: 'minerva-menu-icon-select-dropdown minerva-scrollbar-styled' },
} as const

/** Build select options; include current value when it is not in the curated list. */
function buildIconOptions(current: string | null | undefined): SelectProps['options'] {
  const names = new Set(MENU_ICON_NAMES)
  if (current && !names.has(current)) names.add(current)
  return [...names].sort().map((name) => ({ value: name, label: name }))
}

/** Ant Design icon name picker for menu form (searchable select with preview). */
export function MenuIconSelect({ value, onChange }: MenuIconSelectProps) {
  const { t } = useTranslation()
  const options = useMemo(() => buildIconOptions(value), [value])

  return (
    <Select
      allowClear
      showSearch
      placeholder={t('menuConfig.fields.iconPlaceholder')}
      value={value ?? undefined}
      options={options}
      optionRender={(option) => (
        <Space size="small" className="minerva-menu-icon-select__option">
          {resolveMenuIcon(option.value as string)}
          <span>{option.label}</span>
        </Space>
      )}
      labelRender={(props) => {
        const name = String(props.value ?? '')
        if (!name) return null
        return (
          <Space size="small" className="minerva-menu-icon-select__option">
            {menuIconMap[name] ?? resolveMenuIcon(name)}
            <span>{name}</span>
          </Space>
        )
      }}
      filterOption={(input, option) =>
        String(option?.value ?? '')
          .toLowerCase()
          .includes(input.trim().toLowerCase())
      }
      classNames={MENU_ICON_SELECT_POPUP_CLASS_NAMES}
      onChange={(next) => onChange?.(next ?? null)}
    />
  )
}
