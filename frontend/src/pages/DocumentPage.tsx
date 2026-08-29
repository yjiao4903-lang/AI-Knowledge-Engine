import { ArrowLeftOutlined, FileTextOutlined } from '@ant-design/icons';
import { Alert, Breadcrumb, Button, Card, Layout, Space, Spin, Tag, Tree, Typography, message } from 'antd';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import remarkGfm from 'remark-gfm';
import { useDocument, useOpenOriginal, useSections } from '../api/hooks';
import { loadDocumentChunks } from '../api/hooks';
import type { ChunkDetail, Section } from '../api/types';
import ContentTypeTag from '../components/ContentTypeTag';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

interface TocNode {
  key: string;
  title: React.ReactNode;
  children: TocNode[];
}

/** 按 parent_section_id 建树；sections 表的文档根节点（parent 为 null）作为森林根 */
function buildTocTree(sections: Section[]): TocNode[] {
  const byParent = new Map<string | null, Section[]>();
  for (const s of sections) {
    const key = s.parent_section_id;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key)!.push(s);
  }
  const build = (nodes: Section[]): TocNode[] =>
    nodes.map((s) => ({
      key: s.id,
      title: s.heading,
      children: build(byParent.get(s.id) ?? []),
    }));
  return build(byParent.get(null) ?? []);
}

const DocumentPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const targetLine = Number(searchParams.get('line') ?? NaN);
  const targetChunk = searchParams.get('chunk');
  const navigate = useNavigate();

  const docQuery = useDocument(id);
  const sectionsQuery = useSections(id);
  const [chunks, setChunks] = useState<ChunkDetail[] | null>(null);
  const [chunksError, setChunksError] = useState<string | null>(null);
  const [loadingCount, setLoadingCount] = useState(0);
  const [highlightChunkId, setHighlightChunkId] = useState<string | null>(null);
  const chunkRefs = useRef(new Map<string, HTMLDivElement>());
  const openOriginal = useOpenOriginal();

  const sections = sectionsQuery.data?.sections ?? [];
  const tocTree = useMemo(() => buildTocTree(sections), [sections]);

  // 枚举全部 chunk（探针法，见 loadDocumentChunks 注释）
  useEffect(() => {
    if (!id || !sectionsQuery.data) return;
    let cancelled = false;
    setChunks(null);
    setChunksError(null);
    loadDocumentChunks(id, sectionsQuery.data.sections, (loaded) => {
      if (!cancelled) setLoadingCount(loaded);
    })
      .then((cs) => {
        if (!cancelled) setChunks(cs);
      })
      .catch((e) => {
        if (!cancelled) setChunksError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [id, sectionsQuery.data]);

  // 搜索结果跳转：滚动到包含目标行的 chunk 并高亮
  useEffect(() => {
    if (!chunks) return;
    let hit: ChunkDetail | undefined;
    if (targetChunk) {
      hit = chunks.find((c) => c.id === targetChunk);
    }
    if (!hit && Number.isFinite(targetLine)) {
      hit = chunks.find((c) => targetLine >= c.start_line && targetLine <= c.end_line);
    }
    if (!hit && chunks.length > 0) return; // 无目标：停在文档顶部
    if (hit) {
      setHighlightChunkId(hit.id);
      // 等渲染完成再滚动
      requestAnimationFrame(() => {
        chunkRefs.current.get(hit!.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }
  }, [chunks, targetChunk, targetLine]);

  if (docQuery.isError) {
    return (
      <div className="page-container">
        <Alert
          type="error"
          showIcon
          message="文档不存在"
          description={(docQuery.error as Error)?.message}
          action={<Button onClick={() => navigate('/search')}>返回搜索</Button>}
        />
      </div>
    );
  }

  if (docQuery.isLoading || sectionsQuery.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 96 }}>
        <Spin size="large" />
      </div>
    );
  }

  const doc = docQuery.data!;

  const chunksBySection = new Map<string, ChunkDetail[]>();
  for (const c of chunks ?? []) {
    if (!chunksBySection.has(c.section_id)) chunksBySection.set(c.section_id, []);
    chunksBySection.get(c.section_id)!.push(c);
  }

  const scrollToSection = (sectionId: string) => {
    const el = document.getElementById(`sec-${sectionId}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const renderSection = (sec: Section): React.ReactNode => {
    const secChunks = chunksBySection.get(sec.id) ?? [];
    const hasContent = secChunks.length > 0;
    return (
      <div key={sec.id} id={`sec-${sec.id}`} style={{ marginBottom: 16 }}>
        {sec.ordinal > 0 && (
          <Title
            level={Math.min(Math.max(sec.level, 1), 4) as 1 | 2 | 3 | 4}
            style={{ marginTop: 24, marginBottom: 8, scrollMarginTop: 72 }}
            id={`sec-${sec.id}`}
          >
            {sec.heading}
          </Title>
        )}
        {hasContent &&
          secChunks.map((c) => (
            <div
              key={c.id}
              ref={(el) => {
                if (el) chunkRefs.current.set(c.id, el);
                else chunkRefs.current.delete(c.id);
              }}
              className={`md-block ${highlightChunkId === c.id ? 'chunk-highlight' : ''}`}
              style={{ scrollMarginTop: 72 }}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.raw_markdown}</ReactMarkdown>
              <div style={{ textAlign: 'right' }}>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  行 {c.start_line}-{c.end_line} · {c.id}
                </Text>
              </div>
            </div>
          ))}
      </div>
    );
  };

  return (
    <Layout className="doc-layout">
      <Sider width={300} theme="light" className="doc-toc">
        <Text strong style={{ paddingLeft: 12 }}>
          目录
        </Text>
        <Tree
          treeData={tocTree}
          defaultExpandAll
          selectable
          blockNode
          onSelect={(keys) => {
            if (keys.length > 0) scrollToSection(String(keys[0]));
          }}
        />
      </Sider>
      <Content className="doc-content">
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Breadcrumb
            items={[
              { title: <Link to="/search">搜索</Link> },
              { title: doc.id },
            ]}
          />
          <Space wrap>
            <Button size="small" icon={<ArrowLeftOutlined />} onClick={() => navigate('/search')}>
              返回
            </Button>
            <Button
              size="small"
              icon={<FileTextOutlined />}
              loading={openOriginal.isPending}
              onClick={() =>
                openOriginal.mutate(doc.id, {
                  onSuccess: () => void message.success('已调用系统默认程序打开原文'),
                  onError: (e) => void message.error((e as Error).message),
                })
              }
            >
              打开原文 .md
            </Button>
          </Space>
          <Title level={3} style={{ marginTop: 0, marginBottom: 0 }}>
            {doc.title}
          </Title>
          <Space size={6} wrap>
            <Tag color="blue">{doc.id}</Tag>
            {doc.domain && <Tag>{doc.domain}</Tag>}
            <Tag>chunks {doc.chunk_count}</Tag>
            <Tag>sections {doc.section_count}</Tag>
            <ContentTypeTag type="prose" />
          </Space>
        </Space>

        {chunksError && (
          <Alert type="error" showIcon style={{ marginTop: 16 }} message="加载文档内容失败" description={chunksError} />
        )}
        {!chunks && !chunksError && sectionsQuery.data && (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <Spin tip={`正在加载文档内容（已加载 ${loadingCount} chunks）`}>
              <div style={{ height: 80 }} />
            </Spin>
          </div>
        )}
        {chunks && (
          <Card variant="borderless" style={{ marginTop: 16, padding: 0 }}>
            {sections.map((sec) => renderSection(sec))}
          </Card>
        )}
      </Content>
    </Layout>
  );
};

export default DocumentPage;
