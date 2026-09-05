import { Alert, Button, Card, Empty, List, Select, Space, Spin, Tag, Typography, message } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
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
  missing_source: '来源缺失',
  changed_source: '来源变更',
};

const STATUS_LABELS: Record<TopicCandidateStatus, string> = {
  proposed: '待选择',
  accepted: '已选入下一轮',
  rejected: '不研究',
  deferred: '暂缓',
};

const NextResearchPage: React.FC = () => {
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
      message.success(
        `候选已刷新：新增 ${result.refresh.created}，复用 ${result.refresh.reused}${invalid ? `，${invalid} 个 TaskPack 未通过当前 Gate` : ''}`,
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

  return (
    <div className="page-container">
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Title level={3} style={{ marginBottom: 4 }}>下一轮研究候选</Title>
            <Text type="secondary">
              候选来自通过 Gate 的 TaskPack 开放问题/补证需求、DL-04 增量候选与 Dossier 来源变化。
            </Text>
          </div>
          <Alert
            type="info"
            showIcon
            message="这是 KE 研究规划层，不是正式 Cognition 写入"
            description="“选入下一轮”只改变候选审核状态，不会自动创建 Topic、修订 Judgment 或执行 Proposal Apply。"
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
                  <Text code>{item.candidate_id}</Text>
                  {item.source_task_id ? <Tag>Task {item.source_task_id}</Tag> : null}
                  {item.source_analysis_id ? <Tag>Analysis {item.source_analysis_id}</Tag> : null}
                </Space>
                <Title level={4} style={{ marginTop: 0 }}>{item.title}</Title>
                <Paragraph><Text strong>研究问题：</Text>{item.research_question}</Paragraph>
                <Paragraph><Text strong>为什么现在：</Text>{item.why_now}</Paragraph>
                <Paragraph type="secondary"><Text strong>预期研究价值：</Text>{item.expected_research_value}</Paragraph>
                {item.required_evidence.length ? (
                  <Paragraph type="secondary">
                    <Text strong>需要补齐/复核：</Text>{item.required_evidence.join('；')}
                  </Paragraph>
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
          <Empty description="暂无候选。可点击“刷新缺口候选”从已验证研究结果与主题状态生成。" />
        </Card>
      )}
    </div>
  );
};

export default NextResearchPage;
