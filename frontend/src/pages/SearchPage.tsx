import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Collapse, Input, Radio, Space, Spin, Switch, Tag, Tooltip, Typography } from 'antd';
import React, { useState } from 'react';
import { useDocuments, useHealth, useSearch } from '../api/hooks';
import type { DebugInfo, SearchMode, SearchTiming } from '../api/types';
import FiltersBar, { FiltersValue } from '../components/FiltersBar';
import ResultCard, { EmptyResults } from '../components/ResultCard';

const { Text } = Typography;

const TIMING_PHASES: { key: keyof SearchTiming; label: string; color: string }[] = [
  { key: 'embed_ms', label: 'Embed', color: '#5b8ff9' },
  { key: 'dense_ms', label: 'Dense', color: '#5ad8a6' },
  { key: 'terms_ms', label: 'Terms', color: '#f6bd16' },
  { key: 'trigram_ms', label: 'Trigram', color: '#e8684a' },
  { key: 'fusion_ms', label: 'Fusion', color: '#6dc8ec' },
  { key: 'section_ms', label: 'Section', color: '#9270ca' },
  { key: 'rerank_ms', label: 'Rerank', color: '#ff9d4d' },
  { key: 'filter_ms', label: 'Filter', color: '#269a99' },
];

const TimingBar: React.FC<{ timing: SearchTiming }> = ({ timing }) => {
  const total = Math.max(timing.total_ms, 1);
  return (
    <div>
      <div className="timing-bar">
        {TIMING_PHASES.map(({ key, color }) => {
          const v = timing[key] ?? 0;
          return <span key={key} style={{ width: `${(v / total) * 100}%`, background: color }} title={`${key}: ${v}ms`} />;
        })}
      </div>
      <Space size={4} wrap style={{ marginTop: 6 }}>
        {TIMING_PHASES.map(({ key, label, color }) => (
          <Tag key={key} style={{ borderColor: color }}>
            <span style={{ color }}>■</span> {label} {timing[key]}ms
          </Tag>
        ))}
        <Tag color="blue">total {timing.total_ms}ms</Tag>
      </Space>
    </div>
  );
};

const DebugPanel: React.FC<{ debug: DebugInfo }> = ({ debug }) => (
  <div style={{ fontSize: 12 }}>
    <p>
      <Text strong>候选数：</Text>融合前 {debug.candidates_before_filter}
       ｜ boost sections {debug.boosted_sections.length}
       ｜ 各路来源 dense {debug.sources.dense.length} / terms {debug.sources.terms.length} / trigram {debug.sources.trigram.length}
    </p>
    {debug.fused_top.length > 0 && (
      <>
        <Text strong>融合 Top（fused_top）：</Text>
        <pre style={{ maxHeight: 220, overflow: 'auto', background: '#fafafa', padding: 8 }}>
          {JSON.stringify(debug.fused_top, null, 2)}
        </pre>
      </>
    )}
    {debug.rerank.length > 0 && (
      <>
        <Text strong>Rerank trace：</Text>
        <pre style={{ maxHeight: 220, overflow: 'auto', background: '#fafafa', padding: 8 }}>
          {JSON.stringify(debug.rerank, null, 2)}
        </pre>
      </>
    )}
  </div>
);

const SearchPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [rerank, setRerank] = useState(true);
  const [debug, setDebug] = useState(false);
  const [topK, setTopK] = useState(10);
  const [filters, setFilters] = useState<FiltersValue>({});

  const health = useHealth();
  const search = useSearch(health.data?.retrieval?.qdrant_available);
  const documentsQuery = useDocuments();
  const documents = documentsQuery.data?.documents ?? [];

  const runSearch = () => {
    const q = query.trim();
    if (!q) return;
    setSubmittedQuery(q);
    search.mutate({
      query: q,
      filters: {
        document_ids: filters.document_ids ?? [],
        evidence_levels: filters.evidence_levels ?? [],
        content_types: filters.content_types ?? [],
      },
      options: { mode, rerank, top_k: topK, debug },
    });
  };

  const results = search.data?.results ?? [];

  return (
    <div className="page-container">
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              size="large"
              placeholder="输入检索问题，如：HBM4 的接口位宽是多少？"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onPressEnter={runSearch}
              allowClear
            />
            <Button
              size="large"
              type="primary"
              icon={<SearchOutlined />}
              loading={search.isPending}
              onClick={runSearch}
            >
              搜索
            </Button>
          </Space.Compact>

          <FiltersBar documents={documents} value={filters} onChange={setFilters} />

          <Space size={24} wrap>
            <Space size={8}>
              <Text type="secondary">Mode：</Text>
              <Radio.Group
                optionType="button"
                buttonStyle="solid"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                options={[
                  { value: 'hybrid', label: 'Hybrid' },
                  { value: 'dense', label: 'Dense' },
                  { value: 'lexical', label: 'Exact(lexical)' },
                ]}
              />
            </Space>
            <Tooltip title="Reranker 重排（Top24），ADR-010 默认开启">
              <span>
                <Switch size="small" checked={rerank} onChange={setRerank} />{' '}
                <Text>Reranker</Text>
              </span>
            </Tooltip>
            <Tooltip title="展示 timing 分解与各路召回/融合 trace">
              <span>
                <Switch size="small" checked={debug} onChange={setDebug} />{' '}
                <Text>Debug</Text>
              </span>
            </Tooltip>
            <Space size={8}>
              <Text type="secondary">Top-K：</Text>
              <Radio.Group
                optionType="button"
                size="small"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                options={[5, 10, 20].map((n) => ({ value: n, label: String(n) }))}
              />
            </Space>
          </Space>
        </Space>
      </Card>

      {search.isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="检索失败"
          description={(search.error as Error)?.message}
        />
      )}

      {search.data?.fallback_from && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="语义检索暂不可用，当前显示关键词检索结果"
          description={`原请求模式为 ${search.data.fallback_from}；当前实际模式为 lexical。原因：${search.data.fallback_reason ?? '服务不可用'}`}
          action={<Button size="small" onClick={() => setMode('lexical')}>切换为关键词模式</Button>}
        />
      )}

      {search.isPending && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" tip="检索中（GPU 冷启动首次约 30s+1.3s，请稍候）">
            <div style={{ height: 80 }} />
          </Spin>
        </div>
      )}

      {search.data && !search.isPending && (
        <>
          <Space size={8} wrap style={{ marginBottom: 12 }}>
            <Text type="secondary">
              「{search.data.query}」共 {results.length} 条结果（mode: {search.data.mode}
              {rerank ? '，rerank ON' : ''}）
            </Text>
            <Button size="small" icon={<ReloadOutlined />} onClick={runSearch}>
              重跑
            </Button>
          </Space>

          <Collapse
            size="small"
            style={{ marginBottom: 16 }}
            items={[
              {
                key: 'timing',
                label: `Timing 分解（total ${search.data.timing_ms.total_ms}ms）`,
                children: <TimingBar timing={search.data.timing_ms} />,
              },
              ...(search.data.debug
                ? [{ key: 'debug', label: 'Debug trace', children: <DebugPanel debug={search.data.debug} /> }]
                : []),
            ]}
          />

          {results.length === 0 ? (
            <EmptyResults hint="没有匹配结果，试试放宽过滤条件或更换查询词" />
          ) : (
            results.map((r) => <ResultCard key={r.chunk_id} result={r} query={submittedQuery} />)
          )}
        </>
      )}

      {!search.data && !search.isPending && !search.isError && (
        <EmptyResults hint="输入问题开始检索；Filters / Mode / Reranker / Debug 均会作用于真实后端" />
      )}
    </div>
  );
};

export default SearchPage;
