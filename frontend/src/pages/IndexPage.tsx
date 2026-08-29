import { CloudSyncOutlined, RedoOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Col, Descriptions, Row, Select, Space, Statistic, Tag, Typography, message } from 'antd';
import React, { useState } from 'react';
import { useDocuments, useIndexStatus, useReindexDocument, useScan } from '../api/hooks';

const { Text } = Typography;

const COUNT_LABELS: { key: string; label: string; hint: string }[] = [
  { key: 'documents', label: 'Documents', hint: 'documents 表' },
  { key: 'sections', label: 'Sections', hint: 'sections 表' },
  { key: 'chunks', label: 'Chunks', hint: 'chunks 表（SQLite 正文为准，ADR-008）' },
  { key: 'fts_terms', label: 'FTS Terms', hint: 'chunks_fts_terms 虚表' },
  { key: 'fts_trigram', label: 'FTS Trigram', hint: 'chunks_fts_trigram 虚表' },
  { key: 'qdrant_points', label: 'Qdrant Points', hint: 'kb_chunks_v1 collection' },
];

const IndexPage: React.FC = () => {
  const status = useIndexStatus();
  const documentsQuery = useDocuments();
  const scan = useScan();
  const reindex = useReindexDocument();
  const [reindexDoc, setReindexDoc] = useState<string | undefined>();

  const s = status.data;
  const counts = s?.counts;
  const worker = s?.inference_worker;
  const documents = documentsQuery.data?.documents ?? [];

  const runScan = () => {
    scan.mutate(undefined, {
      onSuccess: (r) => void message.success(`扫描完成：${JSON.stringify(r)}`),
      onError: (e) => void message.error(`扫描失败：${(e as Error).message}`),
    });
  };

  const runReindex = () => {
    if (!reindexDoc) return;
    reindex.mutate(reindexDoc, {
      onSuccess: () => void message.success(`文档 ${reindexDoc} 重索引完成`),
      onError: (e) => void message.error(`重索引失败：${(e as Error).message}`),
    });
  };

  return (
    <div className="page-container">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space>
          <Button
            type="primary"
            icon={<CloudSyncOutlined />}
            loading={scan.isPending}
            onClick={runScan}
          >
            触发 Scan（扫描并应用变更）
          </Button>
          <Space.Compact>
            <Select
              showSearch
              placeholder="选择文档重索引…"
              style={{ minWidth: 320 }}
              optionFilterProp="label"
              value={reindexDoc}
              onChange={setReindexDoc}
              options={documents.map((d) => ({ value: d.id, label: `${d.id} · ${d.title}` }))}
            />
            <Button
              icon={<RedoOutlined />}
              disabled={!reindexDoc}
              loading={reindex.isPending}
              onClick={runReindex}
            >
              Reindex
            </Button>
          </Space.Compact>
          {status.isFetching && !status.isLoading && <Text type="secondary">自动刷新中…</Text>}
        </Space>

        {status.isError && (
          <Alert type="error" showIcon message="无法获取索引状态" description={(status.error as Error)?.message} />
        )}

        {s && counts && (
          <>
            <Card
              title="四方计数与一致性"
              extra={
                s.consistent ? (
                  <Tag color="success">consistent ✓</Tag>
                ) : (
                  <Tag color="error">inconsistent ✗（考虑运行 repair 或 reindex）</Tag>
                )
              }
            >
              <Row gutter={16}>
                {COUNT_LABELS.map(({ key, label, hint }) => (
                  <Col span={4} key={key}>
                    <Statistic title={label} value={counts[key as keyof typeof counts]} />
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {hint}
                    </Text>
                  </Col>
                ))}
              </Row>
            </Card>

            <Card title="Inference Worker 健康">
              {worker ? (
                <Descriptions size="small" column={3}>
                  <Descriptions.Item label="状态">
                    {worker.alive ? <Tag color="success">alive</Tag> : <Tag color="error">down</Tag>}
                  </Descriptions.Item>
                  <Descriptions.Item label="Device">
                    <Tag color="blue">{worker.device}</Tag>（{worker.device_kind}）
                  </Descriptions.Item>
                  <Descriptions.Item label="CPU Fallback">
                    {worker.fallback_to_cpu ? <Tag color="warning">已降级</Tag> : <Tag color="default">否</Tag>}
                  </Descriptions.Item>
                  <Descriptions.Item label="累计重启">{worker.total_restarts}</Descriptions.Item>
                  <Descriptions.Item label="最近全量扫描">
                    {s.last_full_scan ?? '—'}
                  </Descriptions.Item>
                </Descriptions>
              ) : (
                <Text type="secondary">无数据</Text>
              )}
            </Card>
          </>
        )}
      </Space>
    </div>
  );
};

export default IndexPage;
