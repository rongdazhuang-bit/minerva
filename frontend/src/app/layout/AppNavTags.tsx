import { CloseOutlined } from '@ant-design/icons'
import type { AppNavTag } from '@/app/layout/useAppNavTags'
import { useTranslation } from 'react-i18next'
import './appNavTags.css'

type AppNavTagsProps = {
  tags: AppNavTag[]
  activeKey: string
  onActivate: (key: string) => void
  onClose: (key: string) => void
}

/** Horizontal multi-tag bar replacing the former app-shell breadcrumb. */
export function AppNavTags({
  tags,
  activeKey,
  onActivate,
  onClose,
}: AppNavTagsProps) {
  const { t } = useTranslation()

  return (
    <div className="minerva-nav-tags" role="tablist" aria-label={t('layout.navTags.label')}>
      <div className="minerva-nav-tags__scroll">
        {tags.map((tag) => {
          const active = tag.key === activeKey
          return (
            <button
              key={tag.key}
              type="button"
              role="tab"
              aria-selected={active}
              className={
                active
                  ? 'minerva-nav-tags__item minerva-nav-tags__item--active'
                  : 'minerva-nav-tags__item'
              }
              onClick={() => onActivate(tag.key)}
              title={tag.title}
            >
              <span className="minerva-nav-tags__title">{tag.title}</span>
              {tag.closable ? (
                <span
                  className="minerva-nav-tags__close"
                  role="button"
                  tabIndex={0}
                  aria-label={t('layout.navTags.close', { title: tag.title })}
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose(tag.key)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      e.stopPropagation()
                      onClose(tag.key)
                    }
                  }}
                >
                  <CloseOutlined />
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}
