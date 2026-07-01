import { Checkbox, Form, Select, Space, Tree } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { SysMenuNode } from '@/api/menus'
import { buildTreeData, collectAllKeys } from './menuTreeUtils'

type Props = {
  menuTree: SysMenuNode[]
  checkedKeys: string[]
  onCheckedKeysChange: (keys: string[]) => void
  userOptions: { value: string; label: string }[]
  adminsHint?: string
}

/** Shared menu tree and tenant administrator fields for tenant permission UI. */
export function TenantPermissionFields({
  menuTree,
  checkedKeys,
  onCheckedKeysChange,
  userOptions,
  adminsHint,
}: Props) {
  const { t } = useTranslation()
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [expandAll, setExpandAll] = useState(false)
  const [checkStrictly, setCheckStrictly] = useState(false)

  const treeData = useMemo(() => buildTreeData(menuTree), [menuTree])
  const allKeys = useMemo(() => collectAllKeys(menuTree), [menuTree])

  useEffect(() => {
    setExpandedKeys(expandAll ? allKeys : [])
  }, [expandAll, allKeys])

  return (
    <>
      <Form.Item label={t('permissions.menuLabel')}>
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Space wrap>
            <Checkbox checked={expandAll} onChange={(e) => setExpandAll(e.target.checked)}>
              {t('permissions.expandCollapse')}
            </Checkbox>
            <Checkbox
              checked={checkedKeys.length > 0 && checkedKeys.length === allKeys.length}
              indeterminate={checkedKeys.length > 0 && checkedKeys.length < allKeys.length}
              onChange={(e) => onCheckedKeysChange(e.target.checked ? allKeys : [])}
            >
              {t('permissions.selectAll')}
            </Checkbox>
            <Checkbox
              checked={!checkStrictly}
              onChange={(e) => setCheckStrictly(!e.target.checked)}
            >
              {t('permissions.parentChildLink')}
            </Checkbox>
          </Space>
          <div
            className="minerva-scrollbar-styled"
            style={{
              border: '1px solid var(--minerva-border)',
              borderRadius: 6,
              padding: 8,
              maxHeight: 280,
              overflow: 'auto',
            }}
          >
            <Tree
              checkable
              selectable={false}
              checkStrictly={checkStrictly}
              treeData={treeData}
              expandedKeys={expandedKeys}
              checkedKeys={checkedKeys}
              onExpand={(keys) => setExpandedKeys(keys as string[])}
              onCheck={(checked) => {
                if (Array.isArray(checked)) {
                  onCheckedKeysChange(checked as string[])
                } else {
                  onCheckedKeysChange(checked.checked as string[])
                }
              }}
            />
          </div>
        </Space>
      </Form.Item>
      <Form.Item
        name="admin_user_ids"
        label={t('permissions.adminsLabel')}
        extra={adminsHint ?? t('permissions.adminsHint')}
      >
        <Select
          mode="multiple"
          showSearch
          allowClear
          optionFilterProp="label"
          placeholder={t('permissions.adminsPlaceholder')}
          notFoundContent={t('permissions.noTenantUsers')}
          options={userOptions}
        />
      </Form.Item>
    </>
  )
}
