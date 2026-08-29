import { Button, Card, Empty, Space, Tag, Tooltip, Typography, message } from 'antd';
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { HighlightText } from './highlight';
import ContentTypeTag from './ContentTypeTag';
import EvidenceTag from './EvidenceTag';
import type { SearchResult } from '../api/types';

const { Text, Paragraph } = Typography;

function fmtScore(v: number | null | undefined, digits = 4): string {
  return v == null ? '—' : v.toFixed(digits);
}

const ResultCard: React.FC<{ result: SearchResult; query: string }> = ({ result, query }) => {
  const navigate = useNavigate();
  const s = result.scores;

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

  const rerankBadge =
    s.reranker != null ? (
      <Tooltip title={`Reranker ${fmtScore(s.reranker)}（重排前第 ${s.pre_rerank_rank ?? '—'} 名）`}>
        <Tag color="blue">rerank {fmtScore(s.reranker, 3)}</Tag>
      </Tooltip>
    ) : null;

  return (
    <Card size="small" style={{ marginBottom: 12 }}>
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
            <Text strong style={{ fontSize: 15 }}>
              {result.title}
            </Text>
            <EvidenceTag level={result.evidence_level} />
            <ContentTypeTag type={result.content_type} />
            <Tag>{result.document_id}</Tag>
          </Space>
          {result.heading_path && (
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {result.heading_path}
              </Text>
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
            <Space>
              <Button type="primary" size="small" onClick={openContext}>
                查看上下文
              </Button>
              <Button size="small" onClick={copyCitation}>
                复制引用
              </Button>
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
