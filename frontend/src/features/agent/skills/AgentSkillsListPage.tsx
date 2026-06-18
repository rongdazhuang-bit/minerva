/**
 * Tenant agent skills registry list: INDEX-backed rows, zip upload, and delete.
 */
import {
  DeleteOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Alert, Button, Card, Popconfirm, Space, Table, Tooltip, Typography, Upload } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadProps } from 'antd/es/upload/interface'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  deleteSkill,
  listSkillRegistry,
  uploadSkillPackage,
  type SkillRegistryItem,
} from '@/api/agentSkillsMgmt'
import { useAuth } from '@/app/AuthContext'
import { showAppError, useAppMessage } from '@/app/useAppMessage'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import './AgentSkillsPage.css'

const { Text } = Typography

/** Skills list with registry link, zip upload, and per-skill navigation. */
export function AgentSkillsListPage() {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const navigate = useNavigate()
  const { workspaceId, canManageTenantSkills } = useAuth()
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [skills, setSkills] = useState<SkillRegistryItem[]>([])
  const [page, setPage] = useState(1)

  const loadList = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const data = await listSkillRegistry(workspaceId)
      setSkills(data.skills)
      const maxPage = Math.max(1, Math.ceil(data.skills.length / DEFAULT_PAGE_SIZE) || 1)
      if (page > maxPage) setPage(maxPage)
    } catch (e) {
      showAppError(messageApi, t, e)
    } finally {
      setLoading(false)
    }
  }, [workspaceId, page, t, messageApi])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const pagedSkills = useMemo(() => {
    const start = (page - 1) * DEFAULT_PAGE_SIZE
    return skills.slice(start, start + DEFAULT_PAGE_SIZE)
  }, [skills, page])

  const handleDelete = useCallback(
    async (skillId: string) => {
      if (!workspaceId) return
      try {
        await deleteSkill(workspaceId, skillId)
        void messageApi.success(
          t('agents.skills.deleteSuccess', { defaultValue: '技能已删除' }),
        )
        await loadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      }
    },
    [workspaceId, loadList, messageApi, t],
  )

  const handleUpload = useCallback(
    async (file: File) => {
      if (!workspaceId) return
      setUploading(true)
      try {
        const out = await uploadSkillPackage(workspaceId, file)
        void messageApi.success(
          t('agents.skills.uploadSuccess', {
            defaultValue: '技能包已安装：{{id}}',
            id: out.skill_id,
          }),
        )
        await loadList()
      } catch (e) {
        showAppError(messageApi, t, e)
      } finally {
        setUploading(false)
      }
    },
    [workspaceId, loadList, messageApi, t],
  )

  const uploadProps: UploadProps = {
    accept: '.zip',
    showUploadList: false,
    disabled: !canManageTenantSkills || uploading,
    beforeUpload: (file) => {
      void handleUpload(file)
      return false
    },
  }

  const openSkill = useCallback(
    (skillId: string) => {
      navigate(`/app/agents/skills/${encodeURIComponent(skillId)}`)
    },
    [navigate],
  )

  const enterLabel = t('agents.skills.enter', { defaultValue: '进入' })
  const deleteLabel = t('agents.skills.deleteSkill', { defaultValue: '删除' })

  const columns: ColumnsType<SkillRegistryItem> = [
    {
      title: t('agents.skills.colId', { defaultValue: '技能 ID' }),
      dataIndex: 'id',
      key: 'id',
      width: 220,
      ellipsis: true,
    },
    {
      title: t('agents.skills.colDescription', { defaultValue: '描述' }),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('agents.skills.colFileCount', { defaultValue: '文件数' }),
      dataIndex: 'file_count',
      key: 'file_count',
      width: 96,
      align: 'right',
    },
    {
      title: t('agents.skills.colActions', { defaultValue: '操作' }),
      key: 'actions',
      width: 88,
      align: 'center',
      render: (_, row) => (
        <Space size={2} onClick={(e) => e.stopPropagation()}>
          <Tooltip title={enterLabel}>
            <Button
              type="text"
              size="small"
              icon={<FolderOpenOutlined />}
              aria-label={enterLabel}
              onClick={() => openSkill(row.id)}
            />
          </Tooltip>
          {canManageTenantSkills ? (
            <Tooltip title={deleteLabel}>
              <span>
                <Popconfirm
                  title={t('agents.skills.deleteSkillConfirm', {
                    defaultValue: '确定删除该技能包？此操作不可恢复。',
                  })}
                  onConfirm={() => void handleDelete(row.id)}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={deleteLabel}
                  />
                </Popconfirm>
              </span>
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
  ]

  return (
    <div className="minerva-agent-skills-page">
      <Card className="minerva-agent-skills-page__card" variant="borderless">
        <div className="minerva-agent-skills-page__toolbar">
          <Space wrap>
            <Text strong>{t('agents.skills.title', { defaultValue: '技能管理' })}</Text>
            <Button
              type="link"
              icon={<LinkOutlined />}
              onClick={() => navigate('/app/agents/skills/registry')}
            >
              {t('agents.skills.registry', { defaultValue: '技能注册表 (INDEX.json)' })}
            </Button>
          </Space>
          {canManageTenantSkills ? (
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />} loading={uploading}>
                {t('agents.skills.upload', { defaultValue: '上传技能包' })}
              </Button>
            </Upload>
          ) : null}
        </div>
        {!canManageTenantSkills ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={t('agents.skills.readOnly', {
              defaultValue: '当前账号仅可查看技能列表；上传与删除需租户所有者或管理员权限。',
            })}
          />
        ) : null}
        <div className="minerva-agent-skills-page__table-wrap minerva-scrollbar-styled">
          <Table<SkillRegistryItem>
            className="minerva-agent-skills-page__table"
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={pagedSkills}
            tableLayout="fixed"
            onRow={(record) => ({
              onClick: () => openSkill(record.id),
              style: { cursor: 'pointer' },
            })}
            pagination={{
              current: page,
              pageSize: DEFAULT_PAGE_SIZE,
              total: skills.length,
              showSizeChanger: false,
              onChange: (p) => setPage(p),
            }}
          />
        </div>
      </Card>
    </div>
  )
}
