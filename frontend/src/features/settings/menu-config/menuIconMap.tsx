import {
  ApiOutlined,
  AuditOutlined,
  BarChartOutlined,
  BookOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  IdcardOutlined,
  MenuOutlined,
  PictureOutlined,
  ReadOutlined,
  RobotOutlined,
  ScanOutlined,
  SettingOutlined,
  SlidersOutlined,
  TagsOutlined,
  ThunderboltOutlined,
  TranslationOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

/** Maps Ant Design icon component names to rendered icons for menus. */
export const menuIconMap = {
  ApiOutlined: <ApiOutlined />,
  AuditOutlined: <AuditOutlined />,
  BarChartOutlined: <BarChartOutlined />,
  BookOutlined: <BookOutlined />,
  ClockCircleOutlined: <ClockCircleOutlined />,
  CommentOutlined: <CommentOutlined />,
  DatabaseOutlined: <DatabaseOutlined />,
  DashboardOutlined: <DashboardOutlined />,
  FileSearchOutlined: <FileSearchOutlined />,
  FileTextOutlined: <FileTextOutlined />,
  FolderOpenOutlined: <FolderOpenOutlined />,
  IdcardOutlined: <IdcardOutlined />,
  MenuOutlined: <MenuOutlined />,
  PictureOutlined: <PictureOutlined />,
  ReadOutlined: <ReadOutlined />,
  RobotOutlined: <RobotOutlined />,
  ScanOutlined: <ScanOutlined />,
  SettingOutlined: <SettingOutlined />,
  SlidersOutlined: <SlidersOutlined />,
  TagsOutlined: <TagsOutlined />,
  ThunderboltOutlined: <ThunderboltOutlined />,
  TranslationOutlined: <TranslationOutlined />,
  UnorderedListOutlined: <UnorderedListOutlined />,
  UserOutlined: <UserOutlined />,
} satisfies Record<string, ReactNode>

/** Sorted icon names available in the menu icon picker. */
export const MENU_ICON_NAMES = Object.keys(menuIconMap).sort()

/** Resolve a stored icon name to a React node, with fallback. */
export function resolveMenuIcon(name: string | null | undefined): ReactNode | undefined {
  if (!name) return undefined
  return menuIconMap[name] ?? <MenuOutlined />
}
