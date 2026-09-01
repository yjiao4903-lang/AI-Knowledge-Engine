import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExportOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  RedoOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Alert, App, Button, Card, Modal, Space, Spin, Table, Tag, Typography } from 'antd';
import React from 'react';
import {
  useArchiveTask,
  useOpenTaskFolder,
  useRescanTask,
  useTaskPrompt,
  useTaskProposalCandidates,
  useTasks,
} from '../api/hooks';
import type { TaskInfo, TaskStatus, TaskType } from '../api/types';

const { Text } = Typography;

const TASK_TYPE_LABELS: Record<TaskType, string> = {
  summary: '综述 (summary)',
  comparison: '对比 (comparison)',
  causal_synthesis: '因果合成 (causal_synthesis)',
  tension_extraction: '张力提取 (tension_extraction)',
};

const STATUS_META: Record<TaskStatus, { color: string; label: string }> = {
  READY: { color: 'blue', label: '待处理' },
  PROCESSING: { color: 'processing', label: '处理中' },
  COMPLETED: { color: 'success', label: '已完成' },
  FAILED: { color: 'error', label: '失败' },
  INVALID_RESULT: { color: 'volcano', label: '结果无效' },
  IMPORTED: { color: 'purple', label: '已导入' },
  ARCHIVED: { color: 'default', label: '已归档' },
};

function StatusTag({ status, stale }: { status: TaskStatus; stale: boolean }) {
  const meta = STATUS_META[status] ?? { color: 'default', label: status };
  return (
    <Space size={4}>
      <Tag color={meta.color}>{meta.label}</Tag>
      {['COMPLETED', 'IMPORTED'].includes(status) && stale && <Tag color="warning">证据已过时</Tag>}
    </Space>
  );
}

const TaskCenterPage: React.FC = () => {
  const { message } = App.useApp();
  const tasksQuery = useTasks();
  const rescanTask = useRescanTask();
  const archiveTask = useArchiveTask();
  const openFolder = useOpenTaskFolder();
  const copyPrompt = useTaskPrompt();
  const proposalCandidates = useTaskProposalCandidates();
  const tasks = tasksQuery.data?.tasks ?? [];

  const refresh = () => {
    tasksQuery.refetch().catch(() => undefined);
  };

  const onCopyPrompt = (record: TaskInfo) => {
    copyPrompt.mutate(record.task_id, {
      onSuccess: (r) => {
        void navigator.clipboard.writeText(r.content).then(
          () => void message.success('启动提示词已复制到剪贴板'),
          () => void message.warning('复制失败（剪贴板不可用）'),
        );
      },
      onError: (e) => void message.error(`读取提示词失败：${(e as Error).message}`),
    });
  };

  const onOpenFolder = (record: TaskInfo) => {
    openFolder.mutate(record.task_id, {
      onSuccess: (r) => void message.success(`已打开：${r.path}`),
      onError: (e) => void message.error(`打开失败：${(e as Error).message}`),
    });
  };

  const onRescan = (record: TaskInfo) => {
    rescanTask.mutate(record.task_id, {
      onSuccess: (r) => {
        void message.success(
          r.passed
            ? `Gate 通过（citation_coverage=${r.citation_coverage}）`
            : `Gate 未通过（stale=${r.stale}）`,
        );
        void refresh();
      },
      onError: (e) => void message.error(`重新扫描失败：${(e as Error).message}`),
    });
  };

  const onProposalCandidates = (record: TaskInfo) => {
    proposalCandidates.mutate(record.task_id, {
      onSuccess: (r) => {
        const payloadText = JSON.stringify(r.proposal_payload, null, 2);
        Modal.info({
          title: `Cognition Proposal 候选 · ${record.task_id}`,
          width: 920,
          okText: '关闭',
          content: (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Alert
                type="warning"
                showIcon
                message="只读候选，不会自动写入正式认知"
                description="该 JSON 符合 Cognition Proposal V0.2 候选契约；正式变更仍必须在 Cognition 侧 Preview + Human Apply。"
              />
              <Text>
                候选项 {r.proposal_payload.items.length} 条 · auto_apply={String(r.auto_apply)}
              </Text>
              {r.warnings.length > 0 && (
                <Alert type="warning" message={`转换警告 ${r.warnings.length} 条`} description={r.warnings.join('\n')} />
              )}
              <Button
                icon={<CopyOutlined />}
                onClick={() => {
                  void navigator.clipboard.writeText(payloadText).then(
                    () => void message.success('Proposal payload 已复制'),
                    () => void message.warning('复制失败'),
                  );
                }}
              >
                复制 Proposal JSON
              </Button>
              <pre
                style={{
                  maxHeight: 420,
                  overflow: 'auto',
                  background: '#fafafa',
                  border: '1px solid #eee',
                  padding: 12,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {payloadText}
              </pre>
            </Space>
          ),
        });
      },
      onError: (e) => void message.error(`生成 Proposal 候选失败：${(e as Error).message}`),
    });
  };

  const onArchive = (record: TaskInfo) => {
    Modal.confirm({
      title: '归档任务',
      content: `确定归档任务「${record.task_id}」吗？`,
      okText: '归档',
      cancelText: '取消',
      onOk: () =>
        new Promise<void>((resolve) => {
          archiveTask.mutate(record.task_id, {
            onSuccess: () => {
              void message.success('已归档');
              resolve();
            },
            onError: (e) => {
              void message.error(`归档失败：${(e as Error).message}`);
              resolve();
            },
          });
        }),
    });
  };

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 220,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      width: 180,
      render: (v: TaskType | null) => (v ? TASK_TYPE_LABELS[v] ?? v : '—'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (_: TaskStatus, r: TaskInfo) => <StatusTag status={r.status} stale={r.stale} />,
    },
    { title: '查询', dataIndex: 'query', key: 'query', ellipsis: true },
    {
      title: '证据数',
      dataIndex: 'evidence_count',
      key: 'evidence_count',
      width: 90,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: 'Worker / 模型',
      key: 'worker',
      width: 140,
      render: (_: unknown, r: TaskInfo) =>
        r.worker || r.model ? (
          <Text style={{ fontSize: 12 }}>
            {r.worker ?? '—'}{r.model ? ` · ${r.model}` : ''}
          </Text>
        ) : '—',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 455,
      render: (_: unknown, r: TaskInfo) => (
        <Space size={4} wrap>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => onOpenFolder(r)} disabled={r.status === 'ARCHIVED'}>
            打开目录
          </Button>
          <Button size="small" icon={<CopyOutlined />} onClick={() => onCopyPrompt(r)}>
            启动词
          </Button>
          <Button
            size="small"
            icon={<RedoOutlined />}
            onClick={() => onRescan(r)}
            disabled={!['COMPLETED', 'INVALID_RESULT'].includes(r.status)}
            loading={rescanTask.isPending}
          >
            Gate
          </Button>
          <Button
            size="small"
            icon={<ExportOutlined />}
            onClick={() => onProposalCandidates(r)}
            disabled={!['COMPLETED', 'IMPORTED'].includes(r.status)}
            loading={proposalCandidates.isPending}
          >
            Proposal 候选
          </Button>
          <Button size="small" danger onClick={() => onArchive(r)} disabled={r.status === 'ARCHIVED'}>
            归档
          </Button>
        </Space>
      ),
    },
  ];

  if (tasksQuery.isLoading) {
    return <div style={{ textAlign: 'center', padding: 96 }}><Spin size="large" /></div>;
  }

  return (
    <div className="page-container">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="I8：Task Center 现在是运行/调试控制台"
          description="已移除会固定发送空 evidence_refs 的坏创建入口。TaskPack 必须由显式 EvidenceReference[] 创建；正式产品入口将在 Cognition Evidence Basket 中接入。"
        />

        <Space>
          <Button icon={<SyncOutlined />} onClick={refresh} loading={tasksQuery.isFetching}>刷新</Button>
          {tasksQuery.isFetching && <Text type="secondary">自动轮询中…</Text>}
        </Space>

        {tasksQuery.isError && (
          <Alert type="error" showIcon message="无法加载 TaskPack 列表" description={(tasksQuery.error as Error)?.message} />
        )}

        {tasks.length === 0 ? (
          <Alert
            type="info"
            showIcon
            icon={<InboxOutlined />}
            message="暂无任务"
            description="使用 POST /api/synthesis/tasks 并传入至少一条 EvidenceReference；后续 Cognition Evidence Basket 将调用同一接口。"
          />
        ) : (
          <Card title={<span>Task Center（共 {tasks.length} 个任务）</span>}>
            <Table rowKey="task_id" columns={columns} dataSource={tasks} size="small" pagination={{ pageSize: 20 }} />
          </Card>
        )}

        <Card size="small" title="工作流状态">
          <Space wrap>
            <Tag icon={<InboxOutlined />} color="blue">待处理 READY</Tag>
            <Tag icon={<ClockCircleOutlined />} color="processing">处理中 PROCESSING</Tag>
            <Tag icon={<CheckCircleOutlined />} color="success">已完成 COMPLETED</Tag>
            <Tag icon={<CloseCircleOutlined />} color="error">失败 FAILED</Tag>
            <Tag icon={<CloseCircleOutlined />} color="volcano">结果无效 INVALID_RESULT</Tag>
            <Tag icon={<CheckCircleOutlined />} color="purple">已导入 IMPORTED</Tag>
            <Tag color="default">已归档 ARCHIVED</Tag>
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              External Worker 写回 result.json + DONE → Importer Gate → COMPLETED → Proposal Candidate → Cognition Preview / Human Apply。
            </Text>
          </div>
        </Card>
      </Space>
    </div>
  );
};

export default TaskCenterPage;
