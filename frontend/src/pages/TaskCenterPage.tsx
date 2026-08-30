import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  PlusOutlined,
  RedoOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import React from 'react';
import {
  useArchiveTask,
  useCreateTask,
  useOpenTaskFolder,
  useRescanTask,
  useTaskPrompt,
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
      {status === 'COMPLETED' && stale && <Tag color="warning">证据已过时</Tag>}
    </Space>
  );
}

const TaskCenterPage: React.FC = () => {
  const { message } = App.useApp();
  const tasksQuery = useTasks();
  const createTask = useCreateTask();
  const rescanTask = useRescanTask();
  const archiveTask = useArchiveTask();
  const openFolder = useOpenTaskFolder();
  const copyPrompt = useTaskPrompt();

  const [createOpen, setCreateOpen] = React.useState(false);
  const [form] = Form.useForm();
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
            ? `导入通过（citation_coverage=${r.citation_coverage}）`
            : `导入未通过（stale=${r.stale}）`,
        );
        void refresh();
      },
      onError: (e) => void message.error(`重新扫描失败：${(e as Error).message}`),
    });
  };

  const onArchive = (record: TaskInfo) => {
    Modal.confirm({
      title: '归档任务',
      content: `确定归档任务「${record.task_id}」吗？目录将移入 taskpacks/archive。`,
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

  const onCreate = (values: { task_type: TaskType; query: string }) => {
    createTask.mutate(
      {
        task_type: values.task_type,
        query: values.query,
        evidence_refs: [],
        cognition_context: [],
      },
      {
        onSuccess: (r) => {
          void message.success(`TaskPack 已创建：${r.task_id}（${r.status}）`);
          form.resetFields();
          setCreateOpen(false);
          void refresh();
        },
        onError: (e) => void message.error(`创建失败：${(e as Error).message}`),
      },
    );
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
    {
      title: '查询',
      dataIndex: 'query',
      key: 'query',
      ellipsis: true,
    },
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
            {r.worker ?? '—'}
            {r.model ? ` · ${r.model}` : ''}
          </Text>
        ) : (
          '—'
        ),
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
      width: 320,
      render: (_: unknown, r: TaskInfo) => (
        <Space size={4} wrap>
          <Button
            size="small"
            icon={<FolderOpenOutlined />}
            onClick={() => onOpenFolder(r)}
            disabled={r.status === 'ARCHIVED'}
          >
            打开目录
          </Button>
          <Button size="small" icon={<CopyOutlined />} onClick={() => onCopyPrompt(r)}>
            复制启动词
          </Button>
          <Button
            size="small"
            icon={<RedoOutlined />}
            onClick={() => onRescan(r)}
            disabled={!['COMPLETED', 'INVALID_RESULT'].includes(r.status)}
            loading={rescanTask.isPending}
          >
            刷新
          </Button>
          <Button
            size="small"
            danger
            onClick={() => onArchive(r)}
            disabled={r.status === 'ARCHIVED'}
          >
            归档
          </Button>
        </Space>
      ),
    },
  ];

  if (tasksQuery.isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 96 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div className="page-container">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            创建 TaskPack
          </Button>
          <Button icon={<SyncOutlined />} onClick={refresh} loading={tasksQuery.isFetching}>
            刷新
          </Button>
          {tasksQuery.isFetching && <Text type="secondary">自动轮询中…</Text>}
        </Space>

        {tasksQuery.isError && (
          <Alert
            type="error"
            showIcon
            message="无法加载 TaskPack 列表"
            description={(tasksQuery.error as Error)?.message}
          />
        )}

        {tasks.length === 0 ? (
          <Alert
            type="info"
            showIcon
            icon={<InboxOutlined />}
            message="暂无任务"
            description="创建一个 TaskPack 后，外部 Worker 读取 outbox/ 目录并写回 result.json。"
          />
        ) : (
          <Card title={<span>Task Center（共 {tasks.length} 个任务）</span>}>
            <Table
              rowKey="task_id"
              columns={columns}
              dataSource={tasks}
              size="small"
              pagination={{ pageSize: 20 }}
            />
          </Card>
        )}

        <Card size="small" title="工作流状态机（§40）">
          <Space wrap>
            <Tag icon={<InboxOutlined />} color="blue">
              待处理 READY
            </Tag>
            <Tag icon={<ClockCircleOutlined />} color="processing">
              处理中 PROCESSING
            </Tag>
            <Tag icon={<CheckCircleOutlined />} color="success">
              已完成 COMPLETED
            </Tag>
            <Tag icon={<CloseCircleOutlined />} color="error">
              失败 FAILED
            </Tag>
            <Tag icon={<CloseCircleOutlined />} color="volcano">
              结果无效 INVALID_RESULT
            </Tag>
            <Tag icon={<CheckCircleOutlined />} color="purple">
              已导入 IMPORTED
            </Tag>
            <Tag color="default">已归档 ARCHIVED</Tag>
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">
              Worker 在外部工具中读取 outbox/ 任务包 → 完成写入 result/result.json +
              result/DONE → 此处刷新后由 Importer 执行八步 Gate 导入（§46）。
            </Text>
          </div>
        </Card>
      </Space>

      <Modal
        title="创建 TaskPack"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        okText="创建"
        cancelText="取消"
        confirmLoading={createTask.isPending}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={onCreate} initialValues={{ task_type: 'summary' }}>
          <Form.Item label="任务类型" name="task_type" rules={[{ required: true }]}>
            <Select
              options={Object.entries(TASK_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item
            label="研究查询"
            name="query"
            rules={[{ required: true, message: '请输入研究查询' }]}
          >
            <Input.TextArea
              rows={3}
              placeholder="如：HBM4 对先进封装意味着什么？"
              maxLength={1000}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TaskCenterPage;