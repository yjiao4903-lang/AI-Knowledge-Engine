import {
  CheckOutlined,
  DislikeOutlined,
  LikeOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Card, Empty, Space, Tag, Tooltip, Typography, message } from 'antd';
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import NoteButton from './NoteButton';
import type { RetrievalFeedbackEventType, SearchResult } from '../api/types';
import ContentTypeTag from './ContentTypeTag';
import EvidenceTag from './EvidenceTag';
import { HighlightText } from './highlight';

const { Text, Paragraph } = Typography;

function fmtScore(v: number | null | undefined, digits = 4): string {
  return v == null ? '—' : v.toFixed(digits);
}

interface Props {
  result: SearchResult;
  query: string;
  selected?: boolean;
  onToggleEvidence?: (result: SearchResult) => void;
}

const ResultCard: React.FC<Props> = ({ result, query, selected = false, onToggleEvidence }) => {
  const navigate = useNavigate();
  const s = result.scores;
  const [useful, setUseful] = React.useState<boolean | null>(null);

  const openContext = () => {
    navigate(`/document/${encodeURIComponent(result.document_id)}?line=${result.start_line}&chunk=${encodeURIComponent(result.chunk_id)}`);
  };

  const copyCitation = async () => {
    const text = [
      result.title,
      result.heading_path,
      `chunk_id: ${result.chunk_id}`,
      `行 ${result.start_line}-${result.end_line}`,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      void message.success('引用已复制到剪贴板');
    } catch {
      void message.error('复制失败（剪贴板不可用）');
    }
  };

  const recordFeedback = (
    eventType: RetrievalFeedbackEventType,
    usefulValue: boolean | null,
    selectedValue: boolean | null,
  ) => {
    if (!result.search_id || !result.search_mode || !query.trim()) return;
    void api.retrievalFeedback({
      events: [
        {
          search_id: result.search_id,
          query: query.trim(),
          chunk_id: result.chunk_id,
          document_id: result.document_id,
          rank: result.rank,
          mode: result.search_mode,
          rerank: result.rerank_enabled ?? s.reranker != null,
          event_type: eventType,
          useful: usefulValue,
          selected_as_evidence: selectedValue,
        },
      ],
    }).catch(() => {
      // Feedback is best-effort telemetry and must never block the research workflow.
    });
  };

  const markUseful = (value: boolean) => {
    if (useful === value) return;
    setUseful(value);
    recordFeedback('useful', value, selected);
  };

  const toggleEvidenceWithFeedback = () => {
    if (!onToggleEvidence) return;
    const nextSelected = !selected;
    recordFeedback(
      nextSelected ? 'evidence_select' : 'evidence_remove',
      useful,
      nextSelected,
    );
    onToggleEvidence(result);
  };

  const rerankBadge =
    s.reranker != null ? (
      <Tooltip title={`Reranker ${fmtScore(s.reranker)}（重排前第 ${s.pre_rerank_rank ?? '—'} 名）`}>
        <Tag color="blue">rerank {fmtScore(s.reranker, 3)}</Tag>
      </Tooltip>
    ) : null;

  return (
    <Card size="small" style={{ marginBottom: 12, borderColor: selected ? '#1677ff' : undefined }}>
      <div style={{ display: 'flex', gap: 12 }}>
        <div
          style={{
            minWidth: 34,
            textAlign: 'center',
            fontWeight: 700,
            fontSize: 16,
            color: result.rank <= 3 ? '#1677ff' : '#8c8c8c',
          }}
        >
          #{result.rank}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Space size={6} wrap style={{ marginBottom: 4 }}>
            <Text strong style={{ fontSize: 15 }}>{result.title}</Text>
            <EvidenceTag level={result.evidence_level} />
            <ContentTypeTag type={result.content_type} />
            <Tag>{result.document_id}</Tag>
            {selected && <Tag color="processing">已加入 Evidence</Tag>}
          </Space>
          {result.heading_path && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>{result.heading_path}</Text>
            </div>
          )}
          <Paragraph style={{ marginTop: 6, marginBottom: 8 }} className="snippet">
            <HighlightText text={result.snippet} query={query} />
          </Paragraph>
          <Space size={4} wrap>
            <Tooltip title={`RRF ${fmtScore(s.rrf)} ｜ section_boost ×${fmtScore(s.section_boost, 2)} ｜ dense#${s.dense_rank ?? '—'} terms#${s.terms_rank ?? '—'} trigram#${s.trigram_rank ?? '—'}`}>
              <Tag color="purple">final {fmtScore(s.final)}</Tag>
            </Tooltip>
            {rerankBadge}
            <Tag>行 {result.start_line}-{result.end_line}</Tag>
            <Tag style={{ fontFamily: 'monospace' }}>{result.chunk_id}</Tag>
          </Space>
          <div style={{ marginTop: 8 }}>
            <Space wrap>
              <Button type="primary" size="small" onClick={openContext}>查看上下文</Button>
              <Button size="small" onClick={copyCitation}>复制引用</Button>
              <Tooltip title="只记录个人检索反馈，不会立即改变当前排序">
                <Button
                  size="small"
                  type={useful === true ? 'primary' : 'text'}
                  icon={<LikeOutlined />}
                  onClick={() => markUseful(true)}
                >
                  有用
                </Button>
              </Tooltip>
              <Tooltip title="只记录个人检索反馈，不会立即改变当前排序">
                <Button
                  size="small"
                  type={useful === false ? 'primary' : 'text'}
                  icon={<DislikeOutlined />}
                  onClick={() => markUseful(false)}
                >
                  无用
                </Button>
              </Tooltip>
              {onToggleEvidence && (
                <Button
                  size="small"
                  type={selected ? 'default' : 'dashed'}
                  icon={selected ? <CheckOutlined /> : <PlusOutlined />}
                  onClick={toggleEvidenceWithFeedback}
                >
                  {selected ? '移出 Evidence' : '加入 Evidence'}
                </Button>
              )}
              <NoteButton result={result} />
            </Space>
          </div>
        </div>
      </div>
    </Card>
  );
};

export const EmptyResults: React.FC<{ hint?: string }> = ({ hint }) => (
  <Empty description={hint ?? '暂无结果'} style={{ marginTop: 48 }} />
);

export default ResultCard;
