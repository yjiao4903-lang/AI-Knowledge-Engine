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
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useDossier, useDossiers } from '../api/dossierHooks';
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
  dossier_id?: string;
  cognition_object_ids?: string[];
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
      ｜ dense {debug.sources.dense.length} / terms {debug.sources.terms.length} / trigram {debug.sources.trigram.length}
    </p>
    {debug.fused_top.length > 0 ? (
      <pre style={{ maxHeight: 220, overflow: 'auto', background: '#fafafa', padding: 8 }}>
        {JSON.stringify(debug.fused_top, null, 2)}
      </pre>
    ) : null}
    {debug.rerank.length > 0 ? (
      <pre style={{ maxHeight: 220, overflow: 'auto', background: '#fafafa', padding: 8 }}>
        {JSON.stringify(debug.rerank, null, 2)}
      </pre>
    ) : null}
  </div>
);

const SearchPage: React.FC = () => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const dossierFromUrl = searchParams.get('dossier') ?? undefined;
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('lexical');
  const [rerank, setRerank] = useState(false);
  const [debug, setDebug] = useState(false);
  const [topK, setTopK] = useState(10);
  const [filters, setFilters] = useState<FiltersValue>({});
  const [basket, setBasket] = useState<EvidenceRefInput[]>(loadBasket);
  const [basketOpen, setBasketOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<CreateTaskForm>();
  const selectedDossierId = Form.useWatch('dossier_id', form);

  const health = useHealth();
  const search = useSearch(health.data?.retrieval?.qdrant_available);
  const createTask = useCreateTask();
  const documentsQuery = useDocuments();
  const dossiers = useDossiers();
  const selectedDossier = useDossier(selectedDossierId);
  const documents = documentsQuery.data?.documents ?? [];

  useEffect(() => {
    localStorage.setItem(BASKET_KEY, JSON.stringify(basket));
  }, [basket]);

  const selectedChunkIds = useMemo(() => new Set(basket.map((item) => item.chunk_id)), [basket]);

  const cognitionOptions = useMemo(() => {
    const detail = selectedDossier.data;
    if (!detail) return [];
    const rows = [
      ...detail.sources.topic,
      ...detail.sources.questions,
      ...detail.sources.judgments,
      ...detail.sources.other_cognition,
    ];
    return rows
      .filter((item) => !item.missing && item.object_id)
      .map((item) => ({
        value: item.object_id,
        label: `${item.role} · ${item.title || item.object_id}`,
      }));
  }, [selectedDossier.data]);

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
      dossier_id: dossierFromUrl,
      cognition_object_ids: [],
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
        dossier_id: values.dossier_id || null,
        cognition_object_ids: values.cognition_object_ids ?? [],
        cognition_context: [],
      },
      {
        onSuccess: (created) => {
          const contextText = created.research_context_included ? '（已附研究上下文）' : '';
          void message.success(`TaskPack 已创建：${created.task_id}${contextText}`);
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
      {dossierFromUrl ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`当前研究主题：${dossierFromUrl}`}
          description="搜索仍用于选择 Evidence；创建 TaskPack 时会默认带入这个 Dossier，你可再选择哪些正式 Cognition 对象作为已有认识上下文。"
          action={<Button size="small" onClick={() => navigate('/topics')}>返回主题</Button>}
        />
      ) : null}

      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              size="large"
              placeholder="输入检索问题，如：AI CAPEX 如何影响现金流？"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onPressEnter={runSearch}
              allowClear
            />
            <Button size="large" type="primary" icon={<SearchOutlined />} loading={search.isPending} onClick={runSearch}>
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
                  setRerank(next !== 'lexical');
                }}
                options={[
                  { value: 'lexical', label: '关键词' },
                  { value: 'dense', label: '语义' },
                  { value: 'hybrid', label: '混合' },
                ]}
              />
            </Space>
            <Tooltip title="Reranker 仅用于语义/混合检索；关键词默认关闭">
              <span><Switch size="small" checked={rerank} onChange={setRerank} /> <Text>Reranker</Text></span>
            </Tooltip>
            <Tooltip title="展示 timing 分解与召回 trace">
              <span><Switch size="small" checked={debug} onChange={setDebug} /> <Text>Debug</Text></span>
            </Tooltip>
            <Space size={8}>
              <Text type="secondary">Top-K：</Text>
              <Radio.Group optionType="button" size="small" value={topK} onChange={(e) => setTopK(e.target.value)} options={[5, 10, 20].map((n) => ({ value: n, label: String(n) }))} />
            </Space>
          </Space>
        </Space>
      </Card>

      {basket.length > 0 ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Evidence Basket 已选择 ${basket.length} 条 anchor evidence`}
          description="Evidence 负责支撑事实；Dossier/Cognition Context 负责研究方向与已有认识，二者不会混成匿名上下文。"
          action={
            <Space>
              <Button size="small" onClick={() => setBasketOpen(true)}>查看 Basket</Button>
              <Button size="small" type="primary" icon={<ExperimentOutlined />} onClick={openCreateTask}>创建 TaskPack</Button>
            </Space>
          }
        />
      ) : null}

      {search.isError ? <Alert type="error" showIcon style={{ marginBottom: 16 }} message="检索失败" description={(search.error as Error)?.message} /> : null}
      {search.data?.fallback_from ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="语义检索暂不可用，当前显示关键词检索结果"
          description={`原请求模式为 ${search.data.fallback_from}；当前实际模式为 lexical。原因：${search.data.fallback_reason ?? '服务不可用'}`}
          action={<Button size="small" onClick={() => setMode('lexical')}>切换为关键词模式</Button>}
        />
      ) : null}

      {search.isPending ? (
        <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>
      ) : null}

      {search.data && !search.isPending ? (
        <>
          <Space size={8} wrap style={{ marginBottom: 12 }}>
            <Text type="secondary">「{search.data.query}」共 {results.length} 条结果（mode: {search.data.mode}{rerank ? '，rerank ON' : ''}）</Text>
            <Button size="small" icon={<ReloadOutlined />} onClick={runSearch}>重跑</Button>
          </Space>
          <Collapse
            size="small"
            style={{ marginBottom: 16 }}
            items={[
              { key: 'timing', label: `Timing 分解（total ${search.data.timing_ms.total_ms}ms）`, children: <TimingBar timing={search.data.timing_ms} /> },
              ...(search.data.debug ? [{ key: 'debug', label: 'Debug trace', children: <DebugPanel debug={search.data.debug} /> }] : []),
            ]}
          />
          {results.length === 0 ? (
            <EmptyResults hint="没有匹配结果，试试放宽过滤条件或更换查询词" />
          ) : results.map((result) => (
            <ResultCard key={result.chunk_id} result={result} query={submittedQuery} selected={selectedChunkIds.has(result.chunk_id)} onToggleEvidence={toggleEvidence} />
          ))}
        </>
      ) : null}

      {!search.data && !search.isPending && !search.isError ? (
        <EmptyResults hint="默认关键词工作台不启动语义模型；需要时显式切换为语义/混合检索。" />
      ) : null}

      <EvidenceBasketDrawer
        open={basketOpen}
        items={basket}
        onClose={() => setBasketOpen(false)}
        onRemove={removeEvidence}
        onClear={() => setBasket([])}
        onCreateTask={openCreateTask}
      />

      <Modal
        title="从 Evidence Basket 创建研究 TaskPack"
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
          description="研究主题与 Cognition 是上下文，不是 Evidence；服务端会按 stable ID 重新读取权威 Cognition 正文，浏览器不会提交正文作为事实。"
        />
        <Form
          form={form}
          layout="vertical"
          onFinish={submitTask}
          initialValues={{ task_type: 'summary', evidence_context_mode: 'none', cognition_object_ids: [] }}
        >
          <Form.Item label="研究主题（可选）" name="dossier_id" extra="选择后 TaskPack 会包含 research_brief.md / research_context.json；不选择仍是合法的旧式 Evidence-only TaskPack。">
            <Select
              allowClear
              loading={dossiers.isLoading}
              placeholder="选择 Topic Research Dossier"
              options={(dossiers.data?.dossiers ?? []).map((item) => ({ value: item.dossier_id, label: item.title }))}
              onChange={() => form.setFieldValue('cognition_object_ids', [])}
            />
          </Form.Item>
          <Form.Item
            label="已有认识（可选）"
            name="cognition_object_ids"
            extra="这些正式 Cognition 对象只作为研究上下文。服务端按 stable object ID 重读正文；事实性 claim 仍必须引用 Evidence chunk_id。"
          >
            <Select
              mode="multiple"
              allowClear
              disabled={!selectedDossierId}
              loading={selectedDossier.isLoading}
              placeholder={selectedDossierId ? '选择要带入新窗口的已有认识' : '先选择研究主题'}
              options={cognitionOptions}
              optionFilterProp="label"
            />
          </Form.Item>
          {selectedDossier.data?.needs_refresh ? (
            <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="所选主题存在来源更新/缺失；TaskPack 会保留该警告，外部 Worker 不得假装上下文完整。" />
          ) : null}
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true }]}>
            <Select options={TASK_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            label="Evidence 上下文"
            name="evidence_context_mode"
            rules={[{ required: true }]}
            extra="默认仅使用选中 chunk；扩大后仍保持每条 chunk 的独立 identity。"
          >
            <Radio.Group optionType="button" buttonStyle="solid" options={CONTEXT_MODE_OPTIONS} />
          </Form.Item>
          <Form.Item label="研究问题" name="query" rules={[{ required: true, whitespace: true, message: '请输入研究问题' }]}>
            <Input.TextArea rows={4} maxLength={1000} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default SearchPage;
