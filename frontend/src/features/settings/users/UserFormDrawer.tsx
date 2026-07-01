import { Alert, Button, Drawer, Form, Input, Radio, Select, Space, TreeSelect } from 'antd'
import type { TreeSelectProps } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type {
  SysUserCapabilities,
  SysUserCreateBody,
  SysUserDepartmentNode,
  SysUserRoleOption,
  SysUserTenantOption,
  SysUserWorkspaceOption,
} from '@/api/users'
import {
  getUserCapabilities,
  listUserAssignableRoles,
  listUserDepartmentTree,
  listUserFormTenants,
  listUserFormWorkspaces,
} from '@/api/users'

/** Form values for create/edit user drawer. */
export type UserFormValues = {
  email: string
  password?: string
  nickname: string
  phone?: string | null
  status?: boolean
  remark?: string | null
  membership_role: string
  department_item_id?: string | null
  role_ids?: string[]
  tenant_id?: string
  workspace_id?: string
}

type SubmitContext = {
  targetWorkspaceId: string
}

type Props = {
  open: boolean
  title: string
  submitting: boolean
  mode: 'create' | 'edit'
  pageWorkspaceId: string | null
  initial?: UserFormValues | null
  onClose: () => void
  onSubmit: (
    values: SysUserCreateBody | Record<string, unknown>,
    context: SubmitContext,
  ) => Promise<void>
}

/** Build Ant Design tree nodes from department API tree. */
function buildDepartmentTreeData(
  nodes: SysUserDepartmentNode[],
): NonNullable<TreeSelectProps['treeData']> {
  return nodes.map((n) => ({
    title: `${n.code} — ${n.name}`,
    value: n.id,
    key: n.id,
    children:
      n.children?.length > 0
        ? buildDepartmentTreeData(n.children)
        : undefined,
  }))
}

/** Map membership_role code to i18n label. */
function membershipRoleLabel(role: string, t: (key: string) => string): string {
  if (role === 'admin') return t('users.membershipAdmin')
  return t('users.membershipMember')
}

/** Right drawer for creating or editing a workspace member. */
export function UserFormDrawer({
  open,
  title,
  submitting,
  mode,
  pageWorkspaceId,
  initial,
  onClose,
  onSubmit,
}: Props) {
  const { t } = useTranslation()
  const [form] = Form.useForm<UserFormValues>()
  const [departments, setDepartments] = useState<SysUserDepartmentNode[]>([])
  const [roles, setRoles] = useState<SysUserRoleOption[]>([])
  const [capabilities, setCapabilities] = useState<SysUserCapabilities | null>(null)
  const [tenants, setTenants] = useState<SysUserTenantOption[]>([])
  const [workspaces, setWorkspaces] = useState<SysUserWorkspaceOption[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(null)
  const [metaLoading, setMetaLoading] = useState(false)

  const showTenantPicker =
    mode === 'create' && capabilities?.can_pick_tenant_workspace === true

  const effectiveWorkspaceId = useMemo(() => {
    if (showTenantPicker) {
      return selectedWorkspaceId ?? pageWorkspaceId
    }
    return pageWorkspaceId
  }, [mode, showTenantPicker, selectedWorkspaceId, pageWorkspaceId])

  const departmentTree = useMemo(
    () => buildDepartmentTreeData(departments),
    [departments],
  )

  const membershipReadonly = useMemo(() => {
    if (mode !== 'edit' || !capabilities?.can_edit_membership_role) return false
    const current = initial?.membership_role
    if (!current) return false
    return !capabilities.assignable_membership_roles.includes(current)
  }, [mode, capabilities, initial?.membership_role])

  const loadWorkspacesForTenant = useCallback(
    async (tenantId: string) => {
      if (!pageWorkspaceId) return []
      const rows = await listUserFormWorkspaces(pageWorkspaceId, tenantId)
      setWorkspaces(rows)
      return rows
    },
    [pageWorkspaceId],
  )

  const handleTenantChange = useCallback(
    async (tenantId: string) => {
      setSelectedTenantId(tenantId)
      setSelectedWorkspaceId(null)
      form.setFieldValue('workspace_id', undefined)
      const rows = await loadWorkspacesForTenant(tenantId)
      if (rows.length > 0) {
        setSelectedWorkspaceId(rows[0].id)
        form.setFieldValue('workspace_id', rows[0].id)
      }
    },
    [form, loadWorkspacesForTenant],
  )

  useEffect(() => {
    if (!open || !pageWorkspaceId) return
    let cancelled = false

    const boot = async () => {
      setMetaLoading(true)
      try {
        const caps = await getUserCapabilities(pageWorkspaceId)
        if (cancelled) return
        setCapabilities(caps)

        if (mode === 'create' && caps.can_pick_tenant_workspace) {
          const tenantRows = await listUserFormTenants(pageWorkspaceId)
          if (cancelled) return
          setTenants(tenantRows)

          const defaultTenantId = caps.default_tenant_id
          const initialTenantId =
            defaultTenantId &&
            tenantRows.some((row) => row.id === defaultTenantId)
              ? defaultTenantId
              : tenantRows[0]?.id ?? null

          if (initialTenantId) {
            setSelectedTenantId(initialTenantId)
            form.setFieldValue('tenant_id', initialTenantId)
            const wsRows = await listUserFormWorkspaces(
              pageWorkspaceId,
              initialTenantId,
            )
            if (cancelled) return
            setWorkspaces(wsRows)
            const initialWorkspaceId = wsRows.some((row) => row.id === pageWorkspaceId)
              ? pageWorkspaceId
              : wsRows[0]?.id ?? null
            if (initialWorkspaceId) {
              setSelectedWorkspaceId(initialWorkspaceId)
              form.setFieldValue('workspace_id', initialWorkspaceId)
            }
          }
        } else {
          setSelectedWorkspaceId(pageWorkspaceId)
        }
      } finally {
        if (!cancelled) setMetaLoading(false)
      }
    }

    void boot()
    return () => {
      cancelled = true
    }
  }, [open, pageWorkspaceId, mode, form])

  useEffect(() => {
    if (!open || !effectiveWorkspaceId) return
    let cancelled = false
    setMetaLoading(true)
    void Promise.all([
      getUserCapabilities(effectiveWorkspaceId),
      listUserDepartmentTree(effectiveWorkspaceId),
      listUserAssignableRoles(effectiveWorkspaceId),
    ])
      .then(([caps, deptRows, roleRows]) => {
        if (cancelled) return
        setCapabilities(caps)
        setDepartments(deptRows)
        setRoles(roleRows)
      })
      .finally(() => {
        if (!cancelled) setMetaLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, effectiveWorkspaceId])

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      email: initial?.email ?? '',
      password: '',
      nickname: initial?.nickname ?? '',
      phone: initial?.phone ?? null,
      status: initial?.status ?? true,
      remark: initial?.remark ?? null,
      membership_role: initial?.membership_role ?? 'member',
      department_item_id: initial?.department_item_id ?? null,
      role_ids: initial?.role_ids ?? [],
    })
  }, [open, initial, form])

  const handleFinish = useCallback(
    async (values: UserFormValues) => {
      const targetWorkspaceId = effectiveWorkspaceId ?? pageWorkspaceId
      if (!targetWorkspaceId) return

      const membershipRole = capabilities?.can_edit_membership_role
        ? values.membership_role
        : 'member'

      if (mode === 'create') {
        await onSubmit(
          {
            email: values.email.trim(),
            password: values.password ?? '',
            nickname: values.nickname.trim(),
            phone: values.phone?.trim() || null,
            status: values.status ?? true,
            remark: values.remark?.trim() || null,
            membership_role: membershipRole,
            department_item_id: values.department_item_id ?? null,
            role_ids: values.role_ids ?? [],
          },
          { targetWorkspaceId },
        )
        return
      }

      const patch: Record<string, unknown> = {
        nickname: values.nickname.trim(),
        phone: values.phone?.trim() || null,
        status: values.status ?? true,
        remark: values.remark?.trim() || null,
        department_item_id: values.department_item_id ?? null,
        role_ids: values.role_ids ?? [],
      }
      if (!membershipReadonly && capabilities?.can_edit_membership_role) {
        patch.membership_role = membershipRole
      }
      if (values.password?.trim()) {
        patch.password = values.password.trim()
      }
      await onSubmit(patch, { targetWorkspaceId: pageWorkspaceId! })
    },
    [
      mode,
      onSubmit,
      effectiveWorkspaceId,
      pageWorkspaceId,
      capabilities,
      membershipReadonly,
    ],
  )

  return (
    <Drawer
      title={title}
      width={520}
      open={open}
      destroyOnClose
      onClose={onClose}
      footer={null}
      classNames={{ body: 'minerva-scrollbar-styled' }}
      extra={
        <Space>
          <Button onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" loading={submitting} onClick={() => void form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      {departments.length === 0 && !metaLoading && !showTenantPicker ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('users.departmentDictMissing')}
        />
      ) : null}
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          name="email"
          label={t('users.email')}
          rules={
            mode === 'create'
              ? [
                  { required: true, message: t('users.emailRequired') },
                  { type: 'email', message: t('users.emailInvalid') },
                ]
              : undefined
          }
        >
          <Input
            allowClear
            disabled={mode === 'edit'}
            placeholder={t('users.emailPlaceholder')}
          />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('users.password')}
          rules={
            mode === 'create'
              ? [
                  { required: true, message: t('users.passwordRequired') },
                  { min: 8, message: t('users.passwordMin') },
                ]
              : [
                  {
                    validator: (_r, v: string | undefined) => {
                      if (!v || !v.trim()) return Promise.resolve()
                      if (v.length < 8) {
                        return Promise.reject(new Error(t('users.passwordMin')))
                      }
                      return Promise.resolve()
                    },
                  },
                ]
          }
        >
          <Input.Password
            allowClear
            placeholder={
              mode === 'edit' ? t('users.passwordEditPlaceholder') : t('users.passwordPlaceholder')
            }
          />
        </Form.Item>
        <Form.Item
          name="nickname"
          label={t('users.nickname')}
          rules={[{ required: true, message: t('users.nicknameRequired') }]}
        >
          <Input allowClear placeholder={t('users.nicknamePlaceholder')} />
        </Form.Item>
        <Form.Item name="phone" label={t('users.phone')}>
          <Input allowClear placeholder={t('users.phonePlaceholder')} />
        </Form.Item>
        <Form.Item name="status" label={t('users.status')} initialValue>
          <Radio.Group>
            <Radio value>{t('users.statusNormal')}</Radio>
            <Radio value={false}>{t('users.statusDisabled')}</Radio>
          </Radio.Group>
        </Form.Item>
        {showTenantPicker ? (
          <>
            <Form.Item
              name="tenant_id"
              label={t('users.tenant')}
              rules={[{ required: true, message: t('users.tenantPlaceholder') }]}
            >
              <Select
                allowClear={false}
                loading={metaLoading}
                placeholder={t('users.tenantPlaceholder')}
                options={tenants.map((row) => ({
                  value: row.id,
                  label: row.name,
                }))}
                onChange={(tenantId: string) => {
                  void handleTenantChange(tenantId)
                }}
              />
            </Form.Item>
            <Form.Item
              name="workspace_id"
              label={t('users.workspace')}
              rules={[{ required: true, message: t('users.workspacePlaceholder') }]}
            >
              <Select
                allowClear={false}
                loading={metaLoading}
                disabled={!selectedTenantId}
                placeholder={t('users.workspacePlaceholder')}
                options={workspaces.map((row) => ({
                  value: row.id,
                  label: row.name,
                }))}
                onChange={(workspaceId: string) => {
                  setSelectedWorkspaceId(workspaceId)
                }}
              />
            </Form.Item>
          </>
        ) : null}
        {capabilities?.can_edit_membership_role ? (
          membershipReadonly ? (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={t('users.membershipRoleReadonlyAdmin')}
              />
              <Form.Item label={t('users.membershipRole')}>
                <Input
                  disabled
                  value={membershipRoleLabel(initial?.membership_role ?? 'member', t)}
                />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              name="membership_role"
              label={t('users.membershipRole')}
              rules={[{ required: true, message: t('users.membershipRoleRequired') }]}
            >
              <Select
                allowClear={false}
                options={capabilities.assignable_membership_roles.map((value) => ({
                  value,
                  label: membershipRoleLabel(value, t),
                }))}
              />
            </Form.Item>
          )
        ) : null}
        <Form.Item name="department_item_id" label={t('users.department')}>
          <TreeSelect
            allowClear
            showSearch
            treeDefaultExpandAll
            loading={metaLoading}
            placeholder={t('users.departmentPlaceholder')}
            treeData={departmentTree}
            treeNodeFilterProp="title"
          />
        </Form.Item>
        <Form.Item name="role_ids" label={t('users.roles')}>
          <Select
            allowClear
            mode="multiple"
            loading={metaLoading}
            placeholder={t('users.rolesPlaceholder')}
            options={roles.map((r) => ({
              value: r.id,
              label: r.role_name,
            }))}
          />
        </Form.Item>
        <Form.Item name="remark" label={t('users.remark')}>
          <Input.TextArea
            allowClear
            rows={3}
            placeholder={t('users.remarkPlaceholder')}
            classNames={{ textarea: 'minerva-scrollbar-styled' }}
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
