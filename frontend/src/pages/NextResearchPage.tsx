import { Alert, Button, Card, Empty, List, Select, Space, Spin, Tag, Typography, message } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDossiers } from '../api/dossierHooks';
import {
  useRefreshTopicCandidates,
  useReviewTopicCandidate,
  useTopicCandidates,
} from '../api/topicCandidateHooks';
import type { TopicCandidateSourceType, TopicCandidateStatus } from '../api/topicCandidateTypes';

const { Paragraph, Text, Title } = Typography;

const SOURCE_LABELS: Record<TopicCandidateSourceType, string> = {
  open_question: '开放问题',
  additional_evidence_needed: '补证需求',
  potential_conflict: '潜在冲突',
  cannot_determine: '无法判断',
  condition_change: '条件变化',
  mechanism_gap: '机制缺口',
  analogy_extension: '类比探索',
  missing_source: '来源缺失',
  changed_source: '来源变更',
};

const STATUS_LABELS: Record<TopicCandidateStatus, string> = {
  proposed: '待选择',
  accepted: '已选入下一轮',
  rejected: '不研究',
  deferred: '暂缓',
};

const PRIORITY_LABELS = { high: '高优先级', medium: '中优先级', low: '低优先级' } as const;
const WORKLOAD_LABELS = { low: '低工作量', medium: '中工作量', high: '高工作量' } as const;
const AVAILABILITY_LABELS = {
  available: '证据可得',
  partial: '部分可得',
  unknown: '可得性待确认',
  blocked: '当前受阻',
} as const;

const NextResearchPage: React.FC = () => {
  const navigate = useNavigate();
  const dossiers = useDossiers();
  const [selectedId, setSelectedId] = useState<string>();
  const candidates = useTopicCandidates(selectedId);
  const refresh = useRefreshTopicCandidates(selectedId);
  const review = useReviewTopicCandidate(selectedId);

  useEffect(() => {
    if (!selectedId && dossiers.data?.dossiers.length) {
      setSelectedId(dossiers.data.dossiers[0].dossier_id);
    }
  }, [dossiers.data, selectedId]);

  const options = useMemo(
    () => (dossiers.data?.dossiers ?? []).map((item) => ({
      value: item.dossier_id,
      label: `${item.title} · ${item.dossier_id}`,
    })),
    [dossiers.data],
  );

  const doRefresh = async () => {
    if (!selectedId) return;
    try {
      const result = await refresh.mutateAsync();
      const invalid = result.refresh.invalid_task_ids.length;
      const omitted = result.refresh.omitted_by_limit;
      message.success(
        `本轮展示 ${result.refresh.selected}/${result.refresh.max_candidates} 个候选（发现 ${result.refresh.signals_discovered} 个信号${omitted ? `，另有 ${omitted} 个按优先级暂不展示` : ''}${invalid ? `，${invalid} 个 TaskPack 未通过当前 Gate` : ''}）`,
      );
    } catch (error) {
      message.error(`刷新失败：${(error as Error).message}`);
    }
  };

  const setStatus = async (candidateId: string, status: TopicCandidateStatus) => {
    try {
      await review.mutateAsync({ candidateId, status });
      message.success(STATUS_LABELS[status]);
    } catch (error) {
      message.error(`审核失败：${(error as Error).message}`);
    }
  };

  const openEvidenceSelection = (candidateId: string, question: string) => {
    if (!selectedId) return;
    const params = new URLSearchParams({
      dossier: selectedId,
      q: question,
      topic_candidate: candidateId,
    });
    navigate(`/search?${params.toString()}`);
  };

  return (
    <div className="page-container">
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Title level={3} style={{ marginBottom: 4 }}>下一轮研究候选</Title>
            <Text type="secondary">
              每次最多展示 5 个可执行候选；可以诚实返回 0 个。排序使用可解释的类别与理由，不制造伪精确分数。
            </Text>
          </div>
          <Alert
            type="info"
            showIcon
            message="这是 KE 研究规划层，不是正式 Cognition 写入"
            description="“选入下一轮”只改变候选审核状态。之后仍需显式选择 Evidence 并创建 TaskPack；不会自动创建 Topic、修订 Judgment、启动 Worker 或执行 Proposal Apply。"
          />
          <Space wrap>
            <Select
              style={{ minWidth: 360 }}
              loading={dossiers.isLoading}
              value={selectedId}
              options={options}
              placeholder="选择研究主题"
              onChange={setSelectedId}
            />
            <Button type="primary" onClick={doRefresh} loading={refresh.isPending} disabled={!selectedId}>
              刷新缺口候选
            </Button>
          </Space>
        </Space>
      </Card>

      {!selectedId ? (
        <Card><Empty description="请先建立并选择一个研究主题" /></Card>
      ) : candidates.isLoading ? (
        <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
      ) : candidates.isError ? (
        <Alert type="error" showIcon message="候选加载失败" description={(candidates.error as Error).message} />
      ) : candidates.data?.candidates.length ? (
        <List
          dataSource={candidates.data.candidates}
          renderItem={(item) => (
            <List.Item>
              <Card style={{ width: '100%' }}>
                <Space wrap style={{ marginBottom: 8 }}>
                  <Tag color={item.status === 'accepted' ? 'green' : item.status === 'rejected' ? 'red' : undefined}>
                    {STATUS_LABELS[item.status]}
                  </Tag>
                  <Tag color="blue">{SOURCE_LABELS[item.source_type]}</Tag>
                  <Tag color={item.priority === 'high' ? 'red' : item.priority === 'low' ? 'default' : 'gold'}>
                    {PRIORITY_LABELS[item.priority]}
                  </Tag>
                  <Tag>{WORKLOAD_LABELS[item.workload_band]}</Tag>
                  <Tag>{AVAILABILITY_LABELS[item.evidence_availability]}</Tag>
                  {item.exploratory ? <Tag color="purple">探索性</Tag> : <Tag color="cyan">判别性</Tag>}
                  <Text code>{item.candidate_id}</Text>
                </Space>
                <Title level={4} style={{ marginTop: 0 }}>{item.title}</Title>
                <Paragraph><Text strong>研究问题：</Text>{item.research_question}</Paragraph>
                <Paragraph><Text strong>与主线关系：</Text>{item.mainline_relevance}</Paragraph>
                <Paragraph><Text strong>为什么现在：</Text>{item.why_now}</Paragraph>
                <Paragraph><Text strong>预期研究增量：</Text>{item.expected_research_value}</Paragraph>
                <Paragraph><Text strong>当前已知：</Text>{item.known.join('；') || '暂无'}</Paragraph>
                <Paragraph><Text strong>当前未知：</Text>{item.unknown.join('；') || '暂无'}</Paragraph>
                {!item.exploratory && item.competing_explanations.length ? (
                  <Paragraph>
                    <Text strong>待区分解释：</Text>{item.competing_explanations.join('；')}
                  </Paragraph>
                ) : null}
                <Paragraph>
                  <Text strong>证据可得性：</Text>{item.evidence_availability_reason}
                </Paragraph>
                <Paragraph>
                  <Text strong>研究范围：</Text>{item.research_scope.join('；') || '未指定'}
                </Paragraph>
                <Paragraph>
                  <Text strong>排除范围：</Text>{item.research_exclusions.join('；') || '未指定'}
                </Paragraph>
                <Paragraph><Text strong>建议方法：</Text>{item.suggested_method}</Paragraph>
                <Paragraph><Text strong>交付物：</Text>{item.deliverable}</Paragraph>
                <Paragraph type="secondary">
                  <Text strong>排序理由：</Text>{item.priority_reason} ｜ <Text strong>工作量：</Text>{item.workload_reason}
                </Paragraph>
                {item.required_evidence.length ? (
                  <Paragraph type="secondary">
                    <Text strong>需要补齐/复核：</Text>{item.required_evidence.join('；')}
                  </Paragraph>
                ) : null}
                {item.duplicate_check === 'possible_duplicate' ? (
                  <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 12 }}
                    message="可能与现有研究问题重复"
                    description={`${item.duplicate_reason}${item.possible_duplicate_refs.length ? ` 相关候选：${item.possible_duplicate_refs.join('、')}` : ''}`}
                  />
                ) : null}
                {item.review_reason ? <Paragraph type="secondary">审核备注：{item.review_reason}</Paragraph> : null}
                <Space wrap>
                  <Button
                    type={item.status === 'accepted' ? 'primary' : 'default'}
                    onClick={() => setStatus(item.candidate_id, 'accepted')}
                    loading={review.isPending}
                  >
                    选入下一轮
                  </Button>
                  {item.status === 'accepted' ? (
                    <Button
                      type="primary"
                      ghost
                      onClick={() => openEvidenceSelection(item.candidate_id, item.research_question)}
                    >
                      去选 Evidence 并建任务
                    </Button>
                  ) : null}
                  <Button onClick={() => setStatus(item.candidate_id, 'deferred')} loading={review.isPending}>
                    暂缓
                  </Button>
                  <Button danger onClick={() => setStatus(item.candidate_id, 'rejected')} loading={review.isPending}>
                    不研究
                  </Button>
                  {item.status !== 'proposed' ? (
                    <Button onClick={() => setStatus(item.candidate_id, 'proposed')} loading={review.isPending}>
                      恢复待选择
                    </Button>
                  ) : null}
                </Space>
              </Card>
            </List.Item>
          )}
        />
      ) : (
        <Card>
          <Empty description="当前没有足够证据支持新的研究方向。系统允许本轮返回 0 个候选。" />
        </Card>
      )}
    </div>
  );
};

export default NextResearchPage;
