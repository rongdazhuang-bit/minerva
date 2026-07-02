import { Modal, Tabs } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { McpClientListItem } from '@/api/mcp'
import { McpResourcesExplorerPanel } from './McpResourcesExplorerPanel'
import { McpToolsExplorerPanel } from './McpToolsExplorerPanel'
import './McpToolExplorerModal.css'

export type McpToolExplorerModalProps = {
  open: boolean
  client: McpClientListItem | null
  workspaceId: string
  onClose: () => void
}

type ExplorerTab = 'tools' | 'resources'

/** Fullscreen MCP tools / resources explorer for one saved client. */
export function McpToolExplorerModal({
  open,
  client,
  workspaceId,
  onClose,
}: McpToolExplorerModalProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<ExplorerTab>('tools')

  useEffect(() => {
    if (open) {
      setActiveTab('tools')
    }
  }, [open, client?.id])

  return (
    <Modal
      open={open}
      title={
        client
          ? t('mcp.toolExplorer.title', {
              defaultValue: 'MCP 工具探索 — {{name}}',
              name: client.name,
            })
          : t('mcp.toolExplorer.titleShort', { defaultValue: 'MCP 工具探索' })
      }
      width="100%"
      centered={false}
      wrapClassName="minerva-mcp-tool-explorer-modal"
      style={{ top: 0, maxWidth: '100vw', padding: 0, margin: 0 }}
      styles={{
        body: {
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
        },
      }}
      footer={null}
      onCancel={onClose}
      destroyOnClose
    >
      <Tabs
        className="minerva-mcp-tool-explorer__tabs"
        style={{ height: '100%' }}
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as ExplorerTab)}
        items={[
            {
              key: 'resources',
              label: t('mcp.toolExplorer.tabResources', { defaultValue: 'Resources' }),
              children: client ? (
                <McpResourcesExplorerPanel
                  client={client}
                  workspaceId={workspaceId}
                  active={activeTab === 'resources'}
                />
              ) : null,
            },
            {
              key: 'tools',
              label: t('mcp.toolExplorer.tabTools', { defaultValue: 'Tools' }),
              children: client ? (
                <McpToolsExplorerPanel client={client} workspaceId={workspaceId} />
              ) : null,
            },
        ]}
      />
    </Modal>
  )
}
