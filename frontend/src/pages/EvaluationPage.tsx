import { Alert, Card, Space, Spin, Table, Tag, Typography } from 'antd';
import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEvaluationLatest } from '../api/hooks';
import type { EvalSummaryMetrics } from '../api/types';

const { Text } = Typography;

const METRIC_LABELS: Record<keyof EvalSummaryMetrics, string> = {
  hit1: 'Hit@1',
  hit3: 'Hit@3',
  hit5: 'Hit@5',
  recall5: 'Recall@5',
  recall10: 'Recall@10',
  mrr: 'MRR@10',
  ndcg: 'NDCG@10',
  p50: 'P50 (ms)',
  p95: 'P95 (ms)',
};

const GATE_LABELS: Record<string, string> = {
  hit5: 'Hit@5 ≥ 0.90',
  mrr: 'MRR@10 ≥ 0.75',
  ndcg: 'NDCG@10 ≥ 0.80',
  exact_hit5: 'Exact Hit@5 ≥ 0.95',
  semantic_hit5: 'Semantic Hit@5 ≥ 0.85',
};

const EvaluationPage: React.FC = () => {
  const evalQuery = useEvaluationLatest();
  const data = evalQuery.data;

  const summaryRows = useMemo(() => {
    if (!data) return [];
    const arms = Object.keys(data.results.summary);
    return arms.map((arm) => ({ key: arm, arm, ...(data.results.summary[arm] ?? {}) }));
  }, [data]);

  const perTypeRows = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.results.per_type).map(([type, v]) => ({
      key: type,
      type,
      n: (v as { n?: number }).n,
      hybrid_rerank_hit5: (v as { hit5?: Record<string, number> }).hit5?.hybrid_rerank,
      hybrid_rerank_mrr: (v as { mrr?: Record<string, number> }).mrr?.hybrid_rerank,
      hybrid_hit5: (v as { hit5?: Record<string, number> }).hit5?.hybrid,
    }));
  }, [data]);

  if (evalQuery.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 96 }}>
        <Spin size="large" />
      </div>
    );
  }
  if (evalQuery.isError) {
    return (
      <div className="page-container">
        <Alert type="error" showIcon message="加载评测结果失败" description={(evalQuery.error as Error)?.message} />
      </div>
    );
  }
  if (!data) return null;

  const gateEntries = Object.entries(data.results.gate ?? {});
  const allPass = gateEntries.every(([, v]) => v);

  return (
    <div className="page-container">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title={`M9 Golden 评测（${data.results.n_queries} 条查询）`}
          extra={allPass ? <Tag color="success">Quality Gate 全部 PASS</Tag> : <Tag color="error">Gate 存在 FAIL</Tag>}
        >
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Space size={8} wrap>
              {gateEntries.map(([k, v]) => (
                <Tag key={k} color={v ? 'success' : 'error'}>
                  {GATE_LABELS[k] ?? k}: {v ? 'PASS' : 'FAIL'}
                </Tag>
              ))}
              <Tag color="blue">best_arm: {data.results.best_arm}</Tag>
              <Tag>index {data.results.index_seconds}s</Tag>
            </Space>
            <Table
              size="small"
              pagination={false}
              dataSource={summaryRows}
              columns={[
                {
                  title: '检索臂（Arm）',
                  dataIndex: 'arm',
                  render: (arm: string) =>
                    arm === data.results.best_arm ? <Text strong>{arm} ★</Text> : arm,
                },
                ...Object.keys(METRIC_LABELS).map((k) => ({
                  title: METRIC_LABELS[k as keyof EvalSummaryMetrics],
                  dataIndex: k,
                  render: (v: number | undefined) => (v == null ? '—' : String(v)),
                })),
              ]}
            />
          </Space>
        </Card>

        <Card title="分类型表现（best arm: hybrid_rerank）">
          <Table
            size="small"
            pagination={false}
            dataSource={perTypeRows}
            columns={[
              { title: '查询类型', dataIndex: 'type' },
              { title: '样本数', dataIndex: 'n' },
              {
                title: 'Hybrid Hit@5',
                dataIndex: 'hybrid_hit5',
                render: (v: number | undefined) => (v == null ? '—' : v.toFixed(2)),
              },
              {
                title: 'Hybrid+Rerank Hit@5',
                dataIndex: 'hybrid_rerank_hit5',
                render: (v: number | undefined) =>
                  v == null ? '—' : <Text type={v >= 0.9 ? 'success' : 'warning'}>{v.toFixed(2)}</Text>,
              },
              {
                title: 'Hybrid+Rerank MRR',
                dataIndex: 'hybrid_rerank_mrr',
                render: (v: number | undefined) => (v == null ? '—' : v.toFixed(2)),
              },
            ]}
          />
        </Card>

        {data.report_markdown && (
          <Card title="评测报告（M9_GOLDEN_EVALUATION.md）">
            <div className="md-block">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.report_markdown}</ReactMarkdown>
            </div>
          </Card>
        )}
      </Space>
    </div>
  );
};

export default EvaluationPage;
