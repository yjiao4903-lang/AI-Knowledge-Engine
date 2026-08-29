import { Alert, Card, Descriptions, Spin, Typography } from 'antd';
import React from 'react';
import { useSettings } from '../api/hooks';

const { Text } = Typography;

const SECTION_LABELS: Record<string, string> = {
  app: '应用',
  knowledge_base: '知识库',
  retrieval: '检索',
  fusion: 'Fusion 融合权重',
  chunking: 'Chunking 参数',
  embedding: 'Embedding',
  reranker: 'Reranker',
  inference: '推理设备',
};

/** 展示 /api/settings 脱敏配置：顶层分组 + 标量字段平铺，嵌套对象折叠为 JSON */
const SettingsPage: React.FC = () => {
  const settings = useSettings();

  if (settings.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 96 }}>
        <Spin size="large" />
      </div>
    );
  }
  if (settings.isError) {
    return (
      <div className="page-container">
        <Alert type="error" showIcon message="加载配置失败" description={(settings.error as Error)?.message} />
      </div>
    );
  }

  const payload = settings.data ?? {};

  return (
    <div className="page-container">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="以下为脱敏后的运行配置（只读）"
      />
      {Object.entries(payload).map(([key, value]) => (
        <Card key={key} size="small" title={SECTION_LABELS[key] ?? key} style={{ marginBottom: 12 }}>
          <Descriptions size="small" column={2} bordered>
            {value !== null && typeof value === 'object'
              ? Object.entries(value as Record<string, unknown>).map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {v !== null && typeof v === 'object' ? (
                      <pre style={{ margin: 0, fontSize: 12 }}>{JSON.stringify(v, null, 2)}</pre>
                    ) : (
                      <Text code>{String(v)}</Text>
                    )}
                  </Descriptions.Item>
                ))
              : (
                  <Descriptions.Item label={key}>
                    <Text code>{String(value)}</Text>
                  </Descriptions.Item>
                )}
          </Descriptions>
        </Card>
      ))}
    </div>
  );
};

export default SettingsPage;
