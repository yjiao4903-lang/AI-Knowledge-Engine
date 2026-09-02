import { ExperimentOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateTask, useDocuments, useHealth, useSearch } from '../api/hooks';
import type {
  DebugInfo,
  EvidenceContextMode,
  EvidenceRefInput,
  SearchMode,
  SearchResult,
  SearchTiming,
  TaskType,
} from '../api/types';
import EvidenceBasketDrawer from '../components/EvidenceBasketDrawer';
import FiltersBar, { FiltersValue } from '../components/FiltersBar';
import ResultCard, { EmptyResults } from '../components/ResultCard';

const { Text } = Typography;
const BASKET_KEY = 'aike:evidence-basket:v1';

const TASK_TYPE_OPTIONS: { value: TaskType; label: string }[] = [
  { value: 'summary', label: '综述 Summary' },
  { value: 'comparison', label: '对比 Comparison' },
  { value: 'causal_synthesis', label: '因果合成 Causal Synthesis' },
  { value: 'tension_extraction', label: '张力提取 Tension Extraction' },
];

const CONTEXT_MODE_OPTIONS: { value: EvidenceContextMode; label: string }[] = [
  { value: 'none', label: '仅选中 Chunk' },
  { value: 'neighbor_1', label: '邻接 ±1 Chunk' },
  { value: 'section', label: '整个 Section' },
];

type CreateTaskForm = {
  task_type: TaskType;
  query: string;
  evidence_context_mode: EvidenceContextMode;
};

function loadBasket(): EvidenceRefInput[] {
  try {
    const raw = localStorage.getItem(BASKET_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && typeof item.chunk_id === 'string');
  } catch {
    return [];
  }
}

function resultToEvidence(result: SearchResult): EvidenceRefInput {
  return {
    source_type: 'report',
    document_id: result.document_id,
    section_id: result.section_id,
    chunk_id: result.chunk_id,
    title: result.title,
    heading_path: result.heading_path,
    start_line: result.start_line,
    end_line: result.end_line,
    evidence_level: result.evidence_level,
    excerpt: result.snippet,
  };
}

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
          return (
            <span
              key={key}
              style={{ width: `${(v / total) * 100}%`, background: color }}
              title={`${key}: ${v}ms`}
            />
          );
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
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  // I8 no-model workbench: deterministic lexical is the default; semantic is explicit.
  const [mode, setMode] = useState<SearchMode>('lexical');
  const [rerank, setRerank] = useState(false);
  const [debug, setDebug] = useState(false);
  const [topK, setTopK] = useState(10);
  const [filters, setFilters] = useState<FiltersValue>({});
  const [basket, setBasket] = useState<EvidenceRefInput[]>(loadBasket);
  const [basketOpen, setBasketOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<CreateTaskForm>();

  const health = useHealth();
  const search = useSearch(health.data?.retrieval?.qdrant_available);
  const createTask = useCreateTask();
  const documentsQuery = useDocuments();
  const documents = documentsQuery.data?.documents ?? [];

  useEffect(() => {
    localStorage.setItem(BASKET_KEY, JSON.stringify(basket));
  }, [basket]);

  const selectedChunkIds = useMemo(() => new Set(basket.map((item) => item.chunk_id)), [basket]);

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

  const toggleEvidence = (result: SearchResult) => {
    setBasket((current) => {
      const exists = current.some((item) => item.chunk_id === result.chunk_id);
      if (exists) return current.filter((item) => item.chunk_id !== result.chunk_id);
      return [...current, resultToEvidence(result)];
    });
  };

  const removeEvidence = (chunkId: string) => {
    setBasket((current) => current.filter((item) => item.chunk_id !== chunkId));
  };

  const openCreateTask = () => {
    if (basket.length === 0) return;
    form.setFieldsValue({
      task_type: 'summary',
      query: submittedQuery || query.trim() || '',
      evidence_context_mode: 'none',
    });
    setCreateOpen(true);
  };

  const submitTask = (values: CreateTaskForm) => {
    createTask.mutate(
      {
        task_type: values.task_type,
        query: values.query.trim(),
        evidence_refs: basket,
        evidence_context_mode: values.evidence_context_mode,
        cognition_context: [],
      },
      {
        onSuccess: (created) => {
          void message.success(`TaskPack 已创建：${created.task_id}`);
          setBasket([]);
          setCreateOpen(false);
          setBasketOpen(false);
          navigate('/tasks');
        },
        onError: (error) => void message.error(`创建 TaskPack 失败：${(error as Error).message}`),
      },
    );
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
              <Text type="secondary">检索：</Text>
              <Radio.Group
                optionType="button"
                buttonStyle="solid"
                value={mode}
                onChange={(e) => {
                  const next = e.target.value as SearchMode;
                  setMode(next);
                  if (next === 'lexical') setRerank(false);
                  else setRerank(true);
                }}
                options={[
                  { value: 'lexical', label: '关键词' },
                  { value: 'dense', label: '语义' },
                  { value: 'hybrid', label: '混合' },
                ]}
              />
            </Space>
            <Tooltip title="Reranker 仅用于语义/混合检索；关键词工作台默认关闭">
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

      {basket.length > 0 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Evidence Basket 已选择 ${basket.length} 条 anchor evidence`}
          description="TaskPack Builder 会按 chunk_id 从权威 catalog 重新解析正文；创建任务时可选择仅当前 chunk、邻接 ±1 或整个 section。"
          action={
            <Space>
              <Button size="small" onClick={() => setBasketOpen(true)}>查看 Basket</Button>
              <Button size="small" type="primary" icon={<ExperimentOutlined />} onClick={openCreateTask}>
                创建 TaskPack
              </Button>
            </Space>
          }
        />
      )}

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
          <Spin size="large" tip={mode === 'lexical' ? '关键词检索中…' : '语义检索中…'}>
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
            <Button size="small" icon={<ReloadOutlined />} onClick={runSearch}>重跑</Button>
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
            results.map((result) => (
              <ResultCard
                key={result.chunk_id}
                result={result}
                query={submittedQuery}
                selected={selectedChunkIds.has(result.chunk_id)}
                onToggleEvidence={toggleEvidence}
              />
            ))
          )}
        </>
      )}

      {!search.data && !search.isPending && !search.isError && (
        <EmptyResults hint="默认关键词工作台不启动语义模型；需要时显式切换为语义/混合检索。" />
      )}

      <EvidenceBasketDrawer
        open={basketOpen}
        items={basket}
        onClose={() => setBasketOpen(false)}
        onRemove={removeEvidence}
        onClear={() => setBasket([])}
        onCreateTask={openCreateTask}
      />

      <Modal
        title="从 Evidence Basket 创建 TaskPack"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="创建 TaskPack"
        confirmLoading={createTask.isPending}
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Anchor evidence：${basket.length} 条`}
          description="上下文扩展只会加入相邻或同 section 的独立 chunk；每条仍保留自己的 chunk_id，外部 Worker 只能引用最终 TaskPack 中显式提供的 Evidence。"
        />
        <Form
          form={form}
          layout="vertical"
          onFinish={submitTask}
          initialValues={{ task_type: 'summary', evidence_context_mode: 'none' }}
        >
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true }]}>
            <Select options={TASK_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="Evidence 上下文"
            name="evidence_context_mode"
            rules={[{ required: true }]}
            extra="默认仅使用选中的 chunk。比较、因果和机制类任务可按需扩大上下文；若扩展后超过 TaskPack 上限会直接提示，不会静默截断。"
          >
            <Radio.Group optionType="button" buttonStyle="solid" options={CONTEXT_MODE_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="研究问题"
            name="query"
            rules={[{ required: true, whitespace: true, message: '请输入研究问题' }]}
          >
            <Input.TextArea rows={4} maxLength={1000} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SearchPage;
