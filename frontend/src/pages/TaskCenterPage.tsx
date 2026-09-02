import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExportOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  SendOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Alert, App, Button, Card, Divider, Dropdown, List, Modal, Space, Spin, Table, Tag, Typography } from 'antd';
import type { MenuProps } from 'antd';
import React from 'react';
import {
  useArchiveTask,
  useCognitionHealth,
  useLaunchWorker,
  useOpenTaskFolder,
  usePublishTaskProposal,
  useRescanTask,
  useTaskDetail,
  useTaskPrompt,
  useTaskProposalCandidates,
  useTasks,
  useWorkerLaunchers,
} from '../api/hooks';
import type { SynthesisClaim, TaskInfo, TaskResultEnvelope, TaskStatus, TaskType } from '../api/types';
import type { WorkerLauncherId } from '../api/workerLauncherTypes';

const { Text, Paragraph, Title } = Typography;

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

function ClaimCard({ claim }: { claim: SynthesisClaim }) {
  return (
    <Card size="small" style={{ marginBottom: 8 }}>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Space wrap>
          <Text code>{claim.id}</Text>
          <Tag>{claim.epistemic_state}</Tag>
        </Space>
        <Paragraph style={{ marginBottom: 0 }}>{claim.text}</Paragraph>
        {claim.evidence_refs?.length > 0 && (
          <div>
            <Text type="secondary">Evidence：</Text>{' '}
            {claim.evidence_refs.map((ref) => <Tag key={ref}>{ref}</Tag>)}
          </div>
        )}
        {claim.rationale && <Text type="secondary">{claim.rationale}</Text>}
      </Space>
    </Card>
  );
}

function ResultViewer({ result }: { result: TaskResultEnvelope }) {
  const claims = result.claims ?? [];
  const tensions = result.tensions ?? [];
  const questions = result.open_questions ?? [];
  const uncertainties = result.uncertainties ?? [];
  const gaps = result.additional_evidence_needed ?? [];

  return (
    <div style={{ maxHeight: '70vh', overflow: 'auto', paddingRight: 8 }}>
      <Space wrap style={{ marginBottom: 12 }}>
        {result.task_type && <Tag>{result.task_type}</Tag>}
        {result.worker?.tool && <Tag color="blue">{result.worker.tool}{result.worker.model ? ` · ${result.worker.model}` : ''}</Tag>}
        {result.generated_at && <Text type="secondary">{result.generated_at}</Text>}
      </Space>
      <Title level={5}>Summary</Title>
      <Paragraph>{result.summary || '—'}</Paragraph>

      <Divider />
      <Title level={5}>Claims（{claims.length}）</Title>
      {claims.length === 0 ? <Text type="secondary">无</Text> : claims.map((claim) => <ClaimCard key={claim.id} claim={claim} />)}

      <Divider />
      <Title level={5}>Tensions（{tensions.length}）</Title>
      {tensions.length === 0 ? (
        <Text type="secondary">无</Text>
      ) : (
        <List
          size="small"
          dataSource={tensions}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={2}>
                <Text>{item.text}</Text>
                <Text type="secondary">{item.evidence_refs?.join(' · ')}</Text>
              </Space>
            </List.Item>
          )}
        />
      )}

      <Divider />
      <Title level={5}>Open Questions（{questions.length}）</Title>
      <List size="small" dataSource={questions} renderItem={(item) => <List.Item>{item}</List.Item>} />

      <Title level={5}>Uncertainties（{uncertainties.length}）</Title>
      <List size="small" dataSource={uncertainties} renderItem={(item) => <List.Item>{item}</List.Item>} />

      <Title level={5}>Additional Evidence Needed（{gaps.length}）</Title>
      <List
        size="small"
        dataSource={gaps}
        renderItem={(item) => (
          <List.Item>
            <Space direction="vertical" size={2}>
              <Text strong>{item.question}</Text>
              <Text type="secondary">{item.reason}</Text>
            </Space>
          </List.Item>
        )}
      />
    </div>
  );
}

const TaskCenterPage: React.FC = () => {
  const { message } = App.useApp();
  const tasksQuery = useTasks();
  const cognitionHealth = useCognitionHealth();
  const workerLaunchers = useWorkerLaunchers();
  const launchWorker = useLaunchWorker();
  const taskDetail = useTaskDetail();
  const rescanTask = useRescanTask();
  const archiveTask = useArchiveTask();
  const openFolder = useOpenTaskFolder();
  const copyPrompt = useTaskPrompt();
  const proposalCandidates = useTaskProposalCandidates();
  const publishProposal = usePublishTaskProposal();
  const tasks = tasksQuery.data?.tasks ?? [];

  const refresh = () => {
    tasksQuery.refetch().catch(() => undefined);
    cognitionHealth.refetch().catch(() => undefined);
    workerLaunchers.refetch().catch(() => undefined);
  };

  const onLaunchWorker = (record: TaskInfo, launcher: WorkerLauncherId) => {
    launchWorker.mutate(
      { taskId: record.task_id, launcher },
      {
        onSuccess: (r) => void message.success(`${r.launcher} 已启动，任务进入 PROCESSING`),
        onError: (e) => void message.error(`启动 Worker 失败：${(e as Error).message}`),
      },
    );
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

  const onViewResult = (record: TaskInfo) => {
    taskDetail.mutate(record.task_id, {
      onSuccess: (detail) => {
        if (!detail.result) {
          void message.warning('该任务暂无可读 result.json');
          return;
        }
        Modal.info({
          title: `Task Result · ${record.task_id}`,
          width: 1000,
          okText: '关闭',
          content: <ResultViewer result={detail.result} />,
        });
      },
      onError: (e) => void message.error(`读取结果失败：${(e as Error).message}`),
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
                message="候选区，不会自动修改正式认知"
                description="正式变更仍必须在 Cognition 侧逐项 Preview + Human Apply。"
              />
              <Text>候选项 {r.proposal_payload.items.length} 条 · auto_apply={String(r.auto_apply)}</Text>
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
              <pre style={{ maxHeight: 420, overflow: 'auto', background: '#fafafa', border: '1px solid #eee', padding: 12, whiteSpace: 'pre-wrap' }}>
                {payloadText}
              </pre>
            </Space>
          ),
        });
      },
      onError: (e) => void message.error(`生成 Proposal 候选失败：${(e as Error).message}`),
    });
  };

  const onPublishProposal = (record: TaskInfo) => {
    Modal.confirm({
      title: '发送到 Cognition Proposal 区',
      content: (
        <Space direction="vertical" size={8}>
          <Text>将任务「{record.task_id}」转换为 Cognition Proposal Candidate。</Text>
          <Text type="secondary">此操作只创建提案，不会执行 Apply、Merge 或判断修订。</Text>
        </Space>
      ),
      okText: '创建 Proposal',
      cancelText: '取消',
      onOk: () =>
        new Promise<void>((resolve) => {
          publishProposal.mutate(record.task_id, {
            onSuccess: (r) => {
              const id = r.publication?.proposal_id ?? 'unknown';
              void message.success(r.reused ? `Proposal 已存在：${id}` : `Proposal 已创建：${id}`);
              Modal.success({
                title: r.reused ? '已复用现有 Proposal' : 'Proposal 已发送到 Cognition',
                content: (
                  <Space direction="vertical">
                    <Text>Proposal ID：<Text code>{id}</Text></Text>
                    <Text type="secondary">下一步请在 Cognition Proposal Center 逐项 Preview / Apply / Reject / Defer。</Text>
                  </Space>
                ),
              });
              resolve();
            },
            onError: (e) => {
              void message.error(`发送 Proposal 失败：${(e as Error).message}`);
              resolve();
            },
          });
        }),
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

  const launcherItems = (workerLaunchers.data?.launchers ?? []).map((item) => ({
    key: item.id,
    label: item.available ? item.label : `${item.label}（未安装 / PATH 不可见）`,
    disabled: !item.available,
  }));
  const hasAvailableLauncher = (workerLaunchers.data?.launchers ?? []).some((item) => item.available);

  const moreItems = (record: TaskInfo): MenuProps['items'] => {
    const items: MenuProps['items'] = [];
    if (record.status !== 'ARCHIVED') {
      items.push({ key: 'folder', label: '打开任务目录', icon: <FolderOpenOutlined /> });
      items.push({ key: 'prompt', label: '复制启动词', icon: <CopyOutlined /> });
    }
    if (['COMPLETED', 'INVALID_RESULT'].includes(record.status)) {
      items.push({ key: 'gate', label: '重新运行 Gate', icon: <RedoOutlined /> });
    }
    if (['COMPLETED', 'IMPORTED'].includes(record.status)) {
      items.push({ key: 'candidate', label: '查看 Proposal 候选', icon: <ExportOutlined /> });
    }
    if (record.status !== 'ARCHIVED') {
      items.push({ key: 'archive', label: '归档任务', danger: true });
    }
    return items;
  };

  const onMoreAction = (record: TaskInfo, key: string) => {
    if (key === 'folder') onOpenFolder(record);
    if (key === 'prompt') onCopyPrompt(record);
    if (key === 'gate') onRescan(record);
    if (key === 'candidate') onProposalCandidates(record);
    if (key === 'archive') onArchive(record);
  };

  const renderActions = (record: TaskInfo) => {
    const resultReadable = ['COMPLETED', 'IMPORTED', 'INVALID_RESULT'].includes(record.status);
    const canPublish = ['COMPLETED', 'IMPORTED'].includes(record.status);
    const menuItems = moreItems(record);

    return (
      <Space size={6} wrap>
        {record.status === 'READY' && (
          hasAvailableLauncher ? (
            <Dropdown
              menu={{
                items: launcherItems,
                onClick: ({ key }) => onLaunchWorker(record, key as WorkerLauncherId),
              }}
              disabled={workerLaunchers.isLoading}
            >
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={launchWorker.isPending}>
                启动 Worker
              </Button>
            </Dropdown>
          ) : (
            <Button size="small" type="primary" icon={<CopyOutlined />} onClick={() => onCopyPrompt(record)} loading={copyPrompt.isPending}>
              复制启动词
            </Button>
          )
        )}

        {record.status === 'PROCESSING' && (
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => onOpenFolder(record)} loading={openFolder.isPending}>
            查看目录
          </Button>
        )}

        {record.status === 'FAILED' && (
          <Button size="small" danger icon={<FolderOpenOutlined />} onClick={() => onOpenFolder(record)} loading={openFolder.isPending}>
            检查失败
          </Button>
        )}

        {resultReadable && (
          <Button size="small" type="primary" icon={<EyeOutlined />} onClick={() => onViewResult(record)} loading={taskDetail.isPending}>
            查看结果
          </Button>
        )}

        {record.status === 'INVALID_RESULT' && (
          <Button size="small" icon={<RedoOutlined />} onClick={() => onRescan(record)} loading={rescanTask.isPending}>
            重新 Gate
          </Button>
        )}

        {canPublish && (
          <Button
            size="small"
            icon={<SendOutlined />}
            onClick={() => onPublishProposal(record)}
            disabled={cognitionHealth.data?.reachable !== true}
            loading={publishProposal.isPending}
          >
            发到 Cognition
          </Button>
        )}

        {record.status === 'ARCHIVED' && <Text type="secondary">已归档</Text>}

        {menuItems.length > 0 && (
          <Dropdown menu={{ items: menuItems, onClick: ({ key }) => onMoreAction(record, key) }}>
            <Button size="small" icon={<MoreOutlined />}>更多</Button>
          </Dropdown>
        )}
      </Space>
    );
  };

  const columns = [
    {
      title: '任务 ID', dataIndex: 'task_id', key: 'task_id', width: 220,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: '类型', dataIndex: 'task_type', key: 'task_type', width: 180,
      render: (v: TaskType | null) => (v ? TASK_TYPE_LABELS[v] ?? v : '—'),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 160,
      render: (_: TaskStatus, r: TaskInfo) => <StatusTag status={r.status} stale={r.stale} />,
    },
    { title: '查询', dataIndex: 'query', key: 'query', ellipsis: true },
    {
      title: '证据数', dataIndex: 'evidence_count', key: 'evidence_count', width: 90,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: 'Worker / 模型', key: 'worker', width: 140,
      render: (_: unknown, r: TaskInfo) =>
        r.worker || r.model ? <Text style={{ fontSize: 12 }}>{r.worker ?? '—'}{r.model ? ` · ${r.model}` : ''}</Text> : '—',
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string | null) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '下一步', key: 'actions', width: 360,
      render: (_: unknown, r: TaskInfo) => renderActions(r),
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
          message="Research Workflow：TaskPack → External Worker → Result → Cognition Proposal"
          description="Task Center 只突出每个状态的当前主要动作；目录、启动词、Gate、候选与归档等辅助操作收进“更多”。正式认知仍必须经过 Cognition Preview + Human Apply。"
        />

        {cognitionHealth.data?.reachable ? (
          <Alert type="success" showIcon message="Cognition Proposal API 已连接" description={cognitionHealth.data.api_url} />
        ) : (
          <Alert
            type="warning"
            showIcon
            message="Cognition Proposal API 当前不可达"
            description={cognitionHealth.data?.error ?? '正在检测；TaskPack 检索与结果查看不受影响。'}
          />
        )}

        {workerLaunchers.isError && (
          <Alert
            type="warning"
            showIcon
            message="Worker Launcher 状态读取失败"
            description="READY 任务仍可使用“复制启动词” + 手工打开目录执行 TaskPack。"
          />
        )}

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
            description="请在搜索页把结果加入 Evidence Basket，然后创建 TaskPack。"
          />
        ) : (
          <Card title={<span>Task Center（共 {tasks.length} 个任务）</span>}>
            <Table rowKey="task_id" columns={columns} dataSource={tasks} size="small" pagination={{ pageSize: 20 }} scroll={{ x: 1300 }} />
          </Card>
        )}

        <Card size="small" title="工作流状态">
          <Space wrap>
            <Tag icon={<InboxOutlined />} color="blue">READY</Tag>
            <Tag icon={<ClockCircleOutlined />} color="processing">PROCESSING</Tag>
            <Tag icon={<CheckCircleOutlined />} color="success">COMPLETED</Tag>
            <Tag icon={<CloseCircleOutlined />} color="error">FAILED</Tag>
            <Tag icon={<CloseCircleOutlined />} color="volcano">INVALID_RESULT</Tag>
            <Tag icon={<CheckCircleOutlined />} color="purple">IMPORTED</Tag>
            <Tag>ARCHIVED</Tag>
          </Space>
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">Launcher → External Worker → result.json + DONE/FAILED → lifecycle supervisor → Importer Gate → Result Viewer → Cognition Proposal → Preview / Human Apply。</Text>
          </div>
        </Card>
      </Space>
    </div>
  );
};

export default TaskCenterPage;
