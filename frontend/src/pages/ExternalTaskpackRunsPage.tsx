import { Alert, Card, Descriptions, Spin, Table, Tag, Typography } from 'antd';
import React from 'react';
import { useExternalRun, useExternalRuns } from '../api/hooks';
import type { ExternalRunTask } from '../api/types';

const { Text, Title } = Typography;
const RUN_ID = 'codex-external-golden32-final-candidate';

const ExternalTaskpackRunsPage: React.FC = () => {
  const runsQuery = useExternalRuns();
  const runQuery = useExternalRun(RUN_ID);
  const run = runQuery.data;
  const tasks = run?.tasks ?? [];

  if (runsQuery.isLoading || runQuery.isLoading) return <div className="page-container"><Spin /> 加载外部归档…</div>;
  if (runsQuery.isError || runQuery.isError) {
    return <div className="page-container"><Alert type="error" message="外部 TaskPack 归档读取失败" description={(runsQuery.error ?? runQuery.error)?.message} /></div>;
  }

  return <div className="page-container">
    <Title level={2}>外部 TaskPack 归档</Title>
    <Text type="secondary">只读评估结果，与普通 Task Center 生命周期分离。</Text>
    <Card title="归档 runs" style={{ marginTop: 16 }}>
      <Table rowKey="run_id" pagination={false} dataSource={runsQuery.data?.runs ?? []}
        columns={[{ title: 'Run ID', dataIndex: 'run_id' }, { title: '任务数', dataIndex: 'task_count' }, { title: '路径', dataIndex: 'path', render: (v: string) => <Text code>{v}</Text> }]} />
    </Card>
    {run && <Card title={`任务详情（${run.run_id}，${run.task_count} 项）`} style={{ marginTop: 16 }}>
      <Table rowKey="task_id" pagination={{ pageSize: 16 }} dataSource={tasks}
        columns={[
          { title: '任务', dataIndex: 'task_id' },
          { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={v === 'COMPLETED' ? 'success' : 'warning'}>{v}</Tag> },
          { title: '类型', dataIndex: 'task_type' },
          { title: 'Query', dataIndex: 'query', ellipsis: true },
          { title: 'Worker / Model', render: (_: unknown, r: ExternalRunTask) => `${r.worker ?? '-'} / ${r.model ?? '-'}` },
          { title: '完成时间', dataIndex: 'completed_at' },
          { title: 'Claims / Tensions', render: (_: unknown, r: ExternalRunTask) => `${r.claims_count} / ${r.tensions_count}` },
        ]} />
      <Descriptions size="small" column={1} style={{ marginTop: 16 }}>
        <Descriptions.Item label="说明">页面仅呈现状态与结果元数据，不展示完整 claims/tensions，也不提供写入操作。</Descriptions.Item>
      </Descriptions>
    </Card>}
  </div>;
};

export default ExternalTaskpackRunsPage;
