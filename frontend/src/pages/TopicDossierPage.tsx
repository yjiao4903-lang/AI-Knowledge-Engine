import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Form,
  Input,
  List,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import React, { useEffect, useMemo, useState } from 'react';
import { useDossier, useDossiers, useUpsertDossier } from '../api/dossierHooks';
import type {
  DossierCognitionSource,
  DossierDetail,
  DossierEvidenceSource,
  DossierUpsertRequest,
} from '../api/dossierTypes';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

type FormValues = {
  dossier_id: string;
  title: string;
  direction?: string;
  scope_include?: string;
  scope_exclude?: string;
  topic_object_id?: string;
  question_ids?: string;
  judgment_ids?: string;
  other_cognition_ids?: string;
};

function lines(value?: string): string[] {
  return (value ?? '')
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joined(values: string[]): string {
  return values.join('\n');
}

const CognitionSourceList: React.FC<{
  title: string;
  items: DossierCognitionSource[];
}> = ({ title, items }) => (
  <Card size="small" title={`${title} · ${items.length}`} style={{ marginBottom: 12 }}>
    {items.length === 0 ? (
      <Text type="secondary">暂无关联</Text>
    ) : (
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item>
            <div style={{ width: '100%' }}>
              <Space wrap>
                <Text strong>{item.title || item.object_id}</Text>
                <Text code>{item.object_id}</Text>
                {item.missing ? <Tag color="red">来源缺失</Tag> : <Tag>正式认知 · 只读</Tag>}
                {item.source_bucket ? <Tag>{item.source_bucket}</Tag> : null}
              </Space>
              {item.excerpt ? (
                <Paragraph type="secondary" ellipsis={{ rows: 3, expandable: true }} style={{ margin: '8px 0 0' }}>
                  {item.excerpt}
                </Paragraph>
              ) : null}
            </div>
          </List.Item>
        )}
      />
    )}
  </Card>
);

const EvidenceSourceList: React.FC<{ items: DossierEvidenceSource[] }> = ({ items }) => (
  <Card size="small" title={`报告证据 · ${items.length}`} style={{ marginBottom: 12 }}>
    {items.length === 0 ? (
      <Text type="secondary">暂无显式 Evidence。后续通过研究任务选择器加入。</Text>
    ) : (
      <List
        size="small"
        dataSource={items}
        renderItem={(item) => (
          <List.Item>
            <div style={{ width: '100%' }}>
              <Space wrap>
                <Text strong>{item.title || item.document_id || item.chunk_id}</Text>
                <Text code>{item.chunk_id}</Text>
                {item.missing ? <Tag color="red">证据缺失</Tag> : <Tag color="blue">Evidence</Tag>}
                {item.start_line != null && item.end_line != null ? (
                  <Tag>{`L${item.start_line}-L${item.end_line}`}</Tag>
                ) : null}
              </Space>
              {item.heading_path ? (
                <div style={{ marginTop: 6 }}><Text type="secondary">{item.heading_path}</Text></div>
              ) : null}
              {item.excerpt ? (
                <Paragraph ellipsis={{ rows: 4, expandable: true }} style={{ margin: '8px 0 0' }}>
                  {item.excerpt}
                </Paragraph>
              ) : null}
            </div>
          </List.Item>
        )}
      />
    )}
  </Card>
);

const Freshness: React.FC<{ detail: DossierDetail }> = ({ detail }) => {
  if (!detail.needs_refresh) {
    return <Alert type="success" showIcon message="来源版本与保存快照一致" />;
  }
  return (
    <Alert
      type="warning"
      showIcon
      message="主题档案需要复核"
      description={
        <Space direction="vertical" size={2}>
          {detail.source_changes.map((change) => (
            <Text key={change.source}>
              <Text code>{change.source}</Text>{' '}
              {change.change === 'missing' ? '已缺失' : change.change === 'changed' ? '内容已更新' : '新增来源'}
            </Text>
          ))}
        </Space>
      }
    />
  );
};

const TopicDossierPage: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string>();
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<FormValues>();
  const dossiers = useDossiers();
  const detail = useDossier(creating ? undefined : selectedId);
  const save = useUpsertDossier();

  useEffect(() => {
    if (!selectedId && !creating && dossiers.data?.dossiers.length) {
      setSelectedId(dossiers.data.dossiers[0].dossier_id);
    }
  }, [creating, dossiers.data, selectedId]);

  useEffect(() => {
    if (creating) {
      form.setFieldsValue({
        dossier_id: '',
        title: '',
        direction: '',
        scope_include: '',
        scope_exclude: '',
        topic_object_id: '',
        question_ids: '',
        judgment_ids: '',
        other_cognition_ids: '',
      });
      return;
    }
    const d = detail.data?.dossier;
    if (!d) return;
    form.setFieldsValue({
      dossier_id: d.dossier_id,
      title: d.title,
      direction: d.direction,
      scope_include: joined(d.scope_include),
      scope_exclude: joined(d.scope_exclude),
      topic_object_id: d.topic_object_id ?? '',
      question_ids: joined(d.question_ids),
      judgment_ids: joined(d.judgment_ids),
      other_cognition_ids: joined(d.other_cognition_ids),
    });
  }, [creating, detail.data, form]);

  const selectedSummary = useMemo(
    () => dossiers.data?.dossiers.find((item) => item.dossier_id === selectedId),
    [dossiers.data, selectedId],
  );

  const beginCreate = () => {
    setSelectedId(undefined);
    setCreating(true);
    form.resetFields();
  };

  const select = (id: string) => {
    setCreating(false);
    setSelectedId(id);
  };

  const submit = async (values: FormValues) => {
    const id = values.dossier_id.trim();
    if (!id) return;
    const existing = !creating ? detail.data?.dossier : undefined;
    const body: DossierUpsertRequest = {
      title: values.title.trim(),
      direction: values.direction?.trim() ?? '',
      scope_include: lines(values.scope_include),
      scope_exclude: lines(values.scope_exclude),
      topic_object_id: values.topic_object_id?.trim() || null,
      question_ids: lines(values.question_ids),
      judgment_ids: lines(values.judgment_ids),
      other_cognition_ids: lines(values.other_cognition_ids),
      // Evidence selection is owned by the research/task workflow. Preserve any
      // existing references when planning metadata is edited from this page.
      evidence_refs: existing?.evidence_refs ?? [],
    };
    try {
      await save.mutateAsync({ id, body });
      message.success(creating ? '研究主题已创建' : '研究主题已保存');
      setCreating(false);
      setSelectedId(id);
    } catch (error) {
      message.error(`保存失败：${(error as Error).message}`);
    }
  };

  return (
    <div className="page-container">
      <Row gutter={16} align="top">
        <Col xs={24} lg={7}>
          <Card
            title="研究主题"
            extra={<Button type="primary" onClick={beginCreate}>新建</Button>}
            style={{ marginBottom: 16 }}
          >
            <Alert
              type="info"
              showIcon
              message="这里保存研究规划，不是正式认知编辑器"
              style={{ marginBottom: 12 }}
            />
            {dossiers.isLoading ? (
              <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>
            ) : dossiers.isError ? (
              <Alert type="error" message="主题列表加载失败" description={(dossiers.error as Error).message} />
            ) : dossiers.data?.dossiers.length ? (
              <List
                size="small"
                dataSource={dossiers.data.dossiers}
                renderItem={(item) => (
                  <List.Item
                    onClick={() => select(item.dossier_id)}
                    style={{ cursor: 'pointer', background: selectedId === item.dossier_id && !creating ? '#fafafa' : undefined, paddingInline: 8 }}
                  >
                    <div style={{ width: '100%' }}>
                      <Space wrap>
                        <Text strong>{item.title}</Text>
                        {item.formal_topic_bound ? <Tag color="green">已绑定 Topic</Tag> : <Tag>Planning</Tag>}
                      </Space>
                      <div><Text type="secondary" code>{item.dossier_id}</Text></div>
                      {item.direction ? <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ margin: '6px 0 0' }}>{item.direction}</Paragraph> : null}
                    </div>
                  </List.Item>
                )}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有研究主题" />
            )}
          </Card>
        </Col>

        <Col xs={24} lg={17}>
          {creating || selectedId ? (
            <>
              <Card title={creating ? '建立研究规划' : selectedSummary?.title ?? '主题设置'} style={{ marginBottom: 16 }}>
                <Form form={form} layout="vertical" onFinish={submit}>
                  <Row gutter={12}>
                    <Col xs={24} md={8}>
                      <Form.Item
                        name="dossier_id"
                        label="Dossier ID"
                        rules={[{ required: true, message: '请输入稳定 ID' }, { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/, message: '仅允许字母、数字、点、下划线、连字符' }]}
                      >
                        <Input disabled={!creating} placeholder="ai-demand-constraint" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={16}>
                      <Form.Item name="title" label="主题标题" rules={[{ required: true, message: '请输入标题' }]}>
                        <Input placeholder="例如：AI 生产率与需求约束" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Form.Item name="direction" label="长期研究方向 / 为什么研究">
                    <TextArea rows={3} placeholder="记录用户明确的研究动机、核心关注与方向，不由点击行为自动改写。" />
                  </Form.Item>
                  <Row gutter={12}>
                    <Col xs={24} md={12}>
                      <Form.Item name="scope_include" label="纳入范围（每行一项）"><TextArea rows={3} /></Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item name="scope_exclude" label="排除范围（每行一项）"><TextArea rows={3} /></Form.Item>
                    </Col>
                  </Row>
                  <Divider orientation="left">正式 Cognition 引用（只读绑定）</Divider>
                  <Alert
                    type="warning"
                    showIcon
                    message="填写的是稳定对象 ID；保存只建立引用，不修改 Cognition"
                    style={{ marginBottom: 12 }}
                  />
                  <Form.Item name="topic_object_id" label="Topic object ID（可空）"><Input placeholder="cog:..." /></Form.Item>
                  <Row gutter={12}>
                    <Col xs={24} md={8}><Form.Item name="question_ids" label="Question IDs"><TextArea rows={3} placeholder="每行一个" /></Form.Item></Col>
                    <Col xs={24} md={8}><Form.Item name="judgment_ids" label="Judgment IDs"><TextArea rows={3} placeholder="每行一个" /></Form.Item></Col>
                    <Col xs={24} md={8}><Form.Item name="other_cognition_ids" label="其他 Cognition IDs"><TextArea rows={3} placeholder="每行一个" /></Form.Item></Col>
                  </Row>
                  <Space>
                    <Button type="primary" htmlType="submit" loading={save.isPending}>保存研究规划</Button>
                    {creating ? <Button onClick={() => { setCreating(false); form.resetFields(); }}>取消</Button> : null}
                  </Space>
                </Form>
              </Card>

              {!creating ? (
                detail.isLoading ? (
                  <div style={{ textAlign: 'center', padding: 64 }}><Spin size="large" /></div>
                ) : detail.isError ? (
                  <Alert type="error" showIcon message="主题档案加载失败" description={(detail.error as Error).message} />
                ) : detail.data ? (
                  <>
                    <Freshness detail={detail.data} />
                    <Card style={{ marginTop: 16, marginBottom: 16 }}>
                      <Space wrap>
                        <Title level={4} style={{ margin: 0 }}>{detail.data.dossier.title}</Title>
                        {detail.data.planning_only ? <Tag>Planning-only</Tag> : <Tag color="green">正式 Topic 已绑定</Tag>}
                        <Tag color="blue">Lexical / model-free</Tag>
                      </Space>
                      {detail.data.dossier.direction ? <Paragraph style={{ marginTop: 12 }}>{detail.data.dossier.direction}</Paragraph> : null}
                      <Space wrap>
                        {detail.data.dossier.scope_include.map((item) => <Tag color="green" key={`in-${item}`}>纳入：{item}</Tag>)}
                        {detail.data.dossier.scope_exclude.map((item) => <Tag key={`out-${item}`}>排除：{item}</Tag>)}
                      </Space>
                    </Card>
                    <CognitionSourceList title="Topic" items={detail.data.sources.topic} />
                    <CognitionSourceList title="关键问题" items={detail.data.sources.questions} />
                    <CognitionSourceList title="当前判断" items={detail.data.sources.judgments} />
                    <CognitionSourceList title="其他正式认知" items={detail.data.sources.other_cognition} />
                    <EvidenceSourceList items={detail.data.sources.evidence} />
                  </>
                ) : null
              ) : null}
            </>
          ) : (
            <Card><Empty description="选择一个主题，或新建研究规划" /></Card>
          )}
        </Col>
      </Row>
    </div>
  );
};

export default TopicDossierPage;
