import { Alert, Card, Select, Space, Typography } from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useTasks } from '../api/hooks';
import ReturnCandidateConsole from '../features/returnCandidates/ReturnCandidateConsole';
import TaskCenterPage from './TaskCenterPage';

const { Text } = Typography;

const TaskCenterWithReturnReviewPage: React.FC = () => {
  const tasksQuery = useTasks();
  const eligible = useMemo(
    () => (tasksQuery.data?.tasks ?? []).filter((task) => ['COMPLETED', 'IMPORTED'].includes(task.status)),
    [tasksQuery.data?.tasks],
  );
  const [taskId, setTaskId] = useState<string | null>(null);

  useEffect(() => {
    if (eligible.length === 0) {
      setTaskId(null);
      return;
    }
    if (!taskId || !eligible.some((task) => task.task_id === taskId)) {
      setTaskId(eligible[0].task_id);
    }
  }, [eligible, taskId]);

  return (
    <>
      <div className="page-container">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="Research Return / Formal Handoff"
            description="仅 COMPLETED / IMPORTED TaskPack 可进入回流候选工作台。Human Review、KE-side Preflight、Cognition Preview 与 Human Apply 保持独立。"
          />
          <Card size="small" title="Return Candidate Console">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space wrap>
                <Text strong>TaskPack：</Text>
                <Select
                  style={{ minWidth: 360 }}
                  value={taskId ?? undefined}
                  placeholder="选择 COMPLETED / IMPORTED TaskPack"
                  loading={tasksQuery.isLoading}
                  onChange={(value) => setTaskId(value)}
                  options={eligible.map((task) => ({
                    value: task.task_id,
                    label: `${task.task_id} · ${task.status} · ${task.query ?? '—'}`,
                  }))}
                />
                <Text type="secondary">候选导入幂等；正式动作始终由 backend gate + Cognition official API 裁决。</Text>
              </Space>
              <ReturnCandidateConsole taskId={taskId} />
            </Space>
          </Card>
        </Space>
      </div>
      <TaskCenterPage />
    </>
  );
};

export default TaskCenterWithReturnReviewPage;
