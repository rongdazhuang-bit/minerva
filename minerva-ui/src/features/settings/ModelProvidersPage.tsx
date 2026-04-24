import { RobotOutlined } from '@ant-design/icons'
import { Card, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import './ModelProvidersPage.css'

const { Title, Paragraph, Text } = Typography

export function ModelProvidersPage() {
  const { t } = useTranslation()

  return (
    <div className="minerva-model-providers">
      <div className="minerva-model-providers__intro">
        <Title level={4} className="minerva-model-providers__title">
          {t('settings.modelProvidersPageTitle')}
        </Title>
        <Paragraph className="minerva-model-providers__lede">{t('settings.modelProvidersPageLede')}</Paragraph>
      </div>

      <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
        <Card
          size="small"
          variant="borderless"
          className="minerva-model-providers__llm"
          title={
            <Space>
              <RobotOutlined />
              {t('settings.llmSectionTitle')}
            </Space>
          }
        >
          <Text type="secondary">{t('settings.llmSectionHint')}</Text>
        </Card>
      </Space>
    </div>
  )
}
