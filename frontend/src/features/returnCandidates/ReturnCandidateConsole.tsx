import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Divider,
  Empty,
  List,
  Modal,
  Radio,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { getReturnCandidateActionPolicy, returnCandidateDisabledReason } from './actionPolicy.js';
import {
  ReturnCandidateApiError,
  returnCandidateApi,
  type EvidenceRole,
  type FormalHandoffResponse,
  type ReturnCandidateBatch,
  type ReturnCandidatePreflight,
  type ReturnCandidateRecord,
  type ReturnReviewStatus,
} from './api';

const { Paragraph, Text, Title } = Typography;

const INTENT_META: Record<string, { color: string; label: string }> = {
  new_judgment: { color: 'green', label: 'new_judgment' },
  add_evidence: { color: 'blue', label: 'add_evidence' },
  revise_judgment: { color: 'gold', label: 'revise_judgment' },
  suggest_retract: { color: 'volcano', label: 'suggest_retract' },
  advance_question: { color: 'purple', label: 'advance_question' },
  relation_change: { color: 'default', label: 'relation_change' },
};

const REVIEW_META: Record<ReturnReviewStatus, { color: string; label: string }> = {
  proposed: { color: 'default', label: '待 Review' },
  accepted: { color: 'success', label: 'accepted' },
  rejected: { color: 'error', label: 'rejected' },
  deferred: { color: 'warning', label: 'deferred' },
};

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre
      style={{
        maxHeight: 260,
        overflow: 'auto',
        background: '#fafafa',
        border: '1px solid #eee',
        borderRadius: 6,
        padding: 10,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function statusError(error: unknown): { message: string; conflict: boolean } {
  if (error instanceof ReturnCandidateApiError) {
    return {
      message: `${error.status ? `HTTP ${error.status} · ` : ''}${error.message}`,
      conflict: error.status === 409,
    };
  }
  return { message: error instanceof Error ? error.message : String(error), conflict: false };
}

function CandidateSummary({ candidate, selected }: { candidate: ReturnCandidateRecord; selected: boolean }) {
  const intent = INTENT_META[candidate.intent] ?? { color: 'default', label: candidate.intent };
  const review = REVIEW_META[candidate.status];
  const targetText = candidate.target_snapshots.length > 0
    ? candidate.target_snapshots.map((target) => `${target.object_type}:${target.object_id}`).join(' · ')
    : 'new object';
  return (
    <div style={{ width: '100%', padding: 8, background: selected ? '#f0f5ff' : undefined, borderRadius: 6 }}>
      <Space wrap size={4}>
        <Tag color={intent.color}>{intent.label}</Tag>
        <Tag color={review.color}>{review.label}</Tag>
        {candidate.has_version_conflict && <Tag color="error">version conflict</Tag>}
        {candidate.version_check_incomplete && <Tag color="warning">version incomplete</Tag>}
      </Space>
      <div style={{ marginTop: 6 }}>
        <Text strong>{candidate.proposed_text}</Text>
      </div>
      <div style={{ marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>{targetText}</Text>
      </div>
    </div>
  );
}

export interface ReturnCandidateConsoleProps {
  taskId: string | null;
}

export const ReturnCandidateConsole: React.FC<ReturnCandidateConsoleProps> = ({ taskId }) => {
  const [batch, setBatch] = useState<ReturnCandidateBatch | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<ReturnCandidatePreflight | null>(null);
  const [handoffResponse, setHandoffResponse] = useState<FormalHandoffResponse | null>(null);
  const [polarity, setPolarity] = useState<EvidenceRole | null>(null);
  const [applyConfirmed, setApplyConfirmed] = useState(false);
  const [serverConflict, setServerConflict] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const selectedCandidate = useMemo(
    () => batch?.candidates.find((candidate) => candidate.candidate_id === selectedId) ?? null,
    [batch, selectedId],
  );
  const handoff = handoffResponse?.formal_handoff ?? null;

  const policy = useMemo(() => getReturnCandidateActionPolicy({
    status: selectedCandidate?.status ?? 'proposed',
    intent: selectedCandidate?.intent ?? 'relation_change',
    preflight,
    handoff,
    polarity,
    formalApplySupported: handoffResponse?.formal_apply_supported === true,
    formalWritePerformed: handoffResponse?.formal_write_performed === true,
    serverConflict,
    applyConfirmed,
  }), [
    selectedCandidate?.status,
    selectedCandidate?.intent,
    preflight,
    handoff,
    polarity,
    handoffResponse?.formal_apply_supported,
    handoffResponse?.formal_write_performed,
    serverConflict,
    applyConfirmed,
  ]);

  const setApiError = useCallback((error: unknown) => {
    const parsed = statusError(error);
    setErrorText(parsed.message);
    if (parsed.conflict) {
      setServerConflict(true);
      setApplyConfirmed(false);
      setPreflight(null);
    }
  }, []);

  const syncHandoff = useCallback(async (activeTaskId: string, candidateId: string) => {
    const next = await returnCandidateApi.formalHandoff(activeTaskId, candidateId);
    setHandoffResponse(next);
    return next;
  }, []);

  const selectCandidate = useCallback((candidateId: string) => {
    setSelectedId(candidateId);
    setPreflight(null);
    setPolarity(null);
    setApplyConfirmed(false);
    setServerConflict(false);
    setErrorText(null);
  }, []);

  const loadTask = useCallback(async (activeTaskId: string) => {
    setLoading(true);
    setErrorText(null);
    setPreflight(null);
    setHandoffResponse(null);
    setPolarity(null);
    setApplyConfirmed(false);
    setServerConflict(false);
    try {
      await returnCandidateApi.ingestResult(activeTaskId);
      const listed = await returnCandidateApi.list(activeTaskId);
      setBatch(listed.return_candidates);
      const currentStillExists = listed.return_candidates.candidates.some(
        (candidate) => candidate.candidate_id === selectedId,
      );
      const nextSelected = currentStillExists
        ? selectedId
        : listed.return_candidates.candidates[0]?.candidate_id ?? null;
      setSelectedId(nextSelected);
      if (nextSelected) {
        await syncHandoff(activeTaskId, nextSelected);
      }
    } catch (error) {
      setBatch(null);
      setSelectedId(null);
      setApiError(error);
    } finally {
      setLoading(false);
    }
  }, [selectedId, setApiError, syncHandoff]);

  useEffect(() => {
    if (!taskId) {
      setBatch(null);
      setSelectedId(null);
      setPreflight(null);
      setHandoffResponse(null);
      return;
    }
    void loadTask(taskId);
  }, [taskId]);

  useEffect(() => {
    if (!taskId || !selectedId) {
      setHandoffResponse(null);
      return;
    }
    let cancelled = false;
    setHandoffResponse(null);
    void returnCandidateApi.formalHandoff(taskId, selectedId)
      .then((response) => {
        if (!cancelled) setHandoffResponse(response);
      })
      .catch((error) => {
        if (!cancelled) setApiError(error);
      });
    return () => { cancelled = true; };
  }, [taskId, selectedId, setApiError]);

  const reloadList = useCallback(async () => {
    if (!taskId) return;
    const listed = await returnCandidateApi.list(taskId);
    setBatch(listed.return_candidates);
    if (selectedId) await syncHandoff(taskId, selectedId);
  }, [taskId, selectedId, syncHandoff]);

  const review = async (status: ReturnReviewStatus) => {
    if (!taskId || !selectedCandidate) return;
    setActionLoading(`review:${status}`);
    setErrorText(null);
    try {
      await returnCandidateApi.review(taskId, selectedCandidate.candidate_id, status);
      await reloadList();
      setPreflight(null);
      setServerConflict(false);
      setApplyConfirmed(false);
    } catch (error) {
      setApiError(error);
    } finally {
      setActionLoading(null);
    }
  };

  const refreshTargets = async () => {
    if (!taskId) return;
    setActionLoading('refresh-targets');
    setErrorText(null);
    try {
      const refreshed = await returnCandidateApi.refreshTargets(taskId);
      setBatch(refreshed.return_candidates);
      setPreflight(null);
      setServerConflict(false);
      setApplyConfirmed(false);
      if (selectedId) await syncHandoff(taskId, selectedId);
    } catch (error) {
      setApiError(error);
    } finally {
      setActionLoading(null);
    }
  };

  const runPreflight = async () => {
    if (!taskId || !selectedCandidate) return;
    setActionLoading('preflight');
    setErrorText(null);
    try {
      const result = await returnCandidateApi.preflight(taskId, selectedCandidate.candidate_id);
      setPreflight(result);
      setServerConflict(false);
      setApplyConfirmed(false);
      await syncHandoff(taskId, selectedCandidate.candidate_id);
    } catch (error) {
      setApiError(error);
    } finally {
      setActionLoading(null);
    }
  };

  const runFormalize = async () => {
    if (!taskId || !selectedCandidate || !policy.canFormalize) return;
    setActionLoading('formalize');
    setErrorText(null);
    try {
      await returnCandidateApi.formalize(taskId, selectedCandidate.candidate_id, polarity);
      await syncHandoff(taskId, selectedCandidate.candidate_id);
    } catch (error) {
      setApiError(error);
      try { await syncHandoff(taskId, selectedCandidate.candidate_id); } catch { /* preserve primary error */ }
    } finally {
      setActionLoading(null);
    }
  };

  const runPreview = async () => {
    if (!taskId || !selectedCandidate || !policy.canPreview) return;
    setActionLoading('preview');
    setErrorText(null);
    try {
      await returnCandidateApi.preview(taskId, selectedCandidate.candidate_id);
      await syncHandoff(taskId, selectedCandidate.candidate_id);
      setApplyConfirmed(false);
    } catch (error) {
      setApiError(error);
      try { await syncHandoff(taskId, selectedCandidate.candidate_id); } catch { /* preserve primary error */ }
    } finally {
      setActionLoading(null);
    }
  };

  const runApply = () => {
    if (!taskId || !selectedCandidate || !policy.canApply) return;
    Modal.confirm({
      title: '确认 Cognition Human Apply',
      content: (
        <Space direction="vertical" size={6}>
          <Text>该操作会通过 Cognition official API 执行正式认知写入。</Text>
          <Text type="secondary">KE 不会 optimistic success；完成后将重新读取 formal handoff / readback。</Text>
        </Space>
      ),
      okText: '确认 Human Apply',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setActionLoading('apply');
        setErrorText(null);
        try {
          await returnCandidateApi.apply(taskId, selectedCandidate.candidate_id);
          await syncHandoff(taskId, selectedCandidate.candidate_id);
          await reloadList();
          setApplyConfirmed(false);
        } catch (error) {
          setApiError(error);
          try { await syncHandoff(taskId, selectedCandidate.candidate_id); } catch { /* preserve primary error */ }
        } finally {
          setActionLoading(null);
        }
      },
    });
  };

  if (!taskId) {
    return <Empty description="请选择一个 COMPLETED / IMPORTED TaskPack" />;
  }

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>;
  }

  if (!batch || batch.candidates.length === 0) {
    return (
      <Space direction="vertical" style={{ width: '100%' }}>
        {errorText && <Alert type="error" showIcon message="Return Candidate API 错误" description={errorText} />}
        <Empty description="该 Worker result 没有可导入的 research_return_candidates" />
      </Space>
    );
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="Worker result → return candidate → Human Review → KE-side Preflight → Formalize → Cognition official Preview → Human Apply → readback"
        description="KE Preflight 与 Cognition Preview 是两个独立步骤；任何 Formal action 都以 backend 返回与 readback 为准，不做纯前端 optimistic success。"
      />

      {errorText && (
        <Alert
          type={serverConflict ? 'warning' : 'error'}
          showIcon
          message={serverConflict ? 'Formal lifecycle 已被 backend conflict gate 阻断' : 'Backend error'}
          description={errorText}
          action={serverConflict ? (
            <Button size="small" onClick={() => void refreshTargets()} loading={actionLoading === 'refresh-targets'}>
              刷新目标状态
            </Button>
          ) : undefined}
        />
      )}

      <Row gutter={12}>
        <Col xs={24} lg={8}>
          <Card size="small" title={`Return Candidates · ${batch.candidates.length}`}>
            <List
              dataSource={batch.candidates}
              renderItem={(candidate) => (
                <List.Item
                  style={{ cursor: 'pointer', paddingInline: 0 }}
                  onClick={() => selectCandidate(candidate.candidate_id)}
                >
                  <CandidateSummary candidate={candidate} selected={candidate.candidate_id === selectedId} />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} lg={16}>
          {!selectedCandidate ? <Empty description="请选择 candidate" /> : (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Card size="small" title="1 · Human Review / Staging">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space wrap>
                    <Tag color={(INTENT_META[selectedCandidate.intent] ?? { color: 'default' }).color}>
                      {selectedCandidate.intent}
                    </Tag>
                    <Tag color={REVIEW_META[selectedCandidate.status].color}>{selectedCandidate.status}</Tag>
                    <Text code>{selectedCandidate.candidate_id}</Text>
                  </Space>
                  <Paragraph style={{ marginBottom: 0 }}><Text strong>Proposed：</Text>{selectedCandidate.proposed_text}</Paragraph>
                  <Paragraph style={{ marginBottom: 0 }}><Text strong>Reason：</Text>{selectedCandidate.reason}</Paragraph>
                  <div>
                    <Text strong>Evidence：</Text>{' '}
                    {selectedCandidate.evidence_chunk_ids.length > 0
                      ? selectedCandidate.evidence_chunk_ids.map((id) => <Tag key={id}>{id}</Tag>)
                      : <Text type="secondary">无直接 evidence chunk</Text>}
                  </div>
                  <div>
                    <Text strong>Source refs：</Text>{' '}
                    {[...selectedCandidate.source_claim_ids, ...selectedCandidate.source_tension_ids].map((id) => <Tag key={id}>{id}</Tag>)}
                    {selectedCandidate.source_open_question_indexes.map((index) => <Tag key={`oq-${index}`}>open_question[{index}]</Tag>)}
                    {selectedCandidate.source_additional_evidence_indexes.map((index) => <Tag key={`ae-${index}`}>additional_evidence[{index}]</Tag>)}
                  </div>
                  <Space wrap>
                    <Button type="primary" onClick={() => void review('accepted')} loading={actionLoading === 'review:accepted'} disabled={policy.applied}>Accept</Button>
                    <Button danger onClick={() => void review('rejected')} loading={actionLoading === 'review:rejected'} disabled={policy.applied}>Reject</Button>
                    <Button onClick={() => void review('deferred')} loading={actionLoading === 'review:deferred'} disabled={policy.applied}>Defer</Button>
                  </Space>
                </Space>
              </Card>

              <Card size="small" title="2 · KE-side Preflight">
                <Alert
                  type="info"
                  showIcon
                  message="KE-side Preflight（只读版本检查，不是 Cognition Preview）"
                  description="这里只比较 KE 派生 Cognition catalog 的 target version；generic preflight 的 formal capability flags 必须保持 false。"
                  style={{ marginBottom: 10 }}
                />
                <Space wrap style={{ marginBottom: 10 }}>
                  <Button onClick={() => void runPreflight()} loading={actionLoading === 'preflight'}>运行 KE-side Preflight</Button>
                  <Button onClick={() => void refreshTargets()} loading={actionLoading === 'refresh-targets'}>刷新 target version</Button>
                </Space>
                {preflight ? (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space wrap>
                      <Tag color={preflight.ke_preflight_only ? 'blue' : 'error'}>ke_preflight_only={String(preflight.ke_preflight_only)}</Tag>
                      <Tag color={preflight.has_version_conflict ? 'error' : 'success'}>conflict={String(preflight.has_version_conflict)}</Tag>
                      <Tag color={preflight.version_check_incomplete ? 'warning' : 'success'}>incomplete={String(preflight.version_check_incomplete)}</Tag>
                      <Tag>formal_preview_supported={String(preflight.formal_preview_supported)}</Tag>
                      <Tag>formal_apply_supported={String(preflight.formal_apply_supported)}</Tag>
                    </Space>
                    {preflight.targets.map((target) => (
                      <Descriptions key={target.object_id} size="small" bordered column={1}>
                        <Descriptions.Item label="Target">{target.object_type} · <Text code>{target.object_id}</Text></Descriptions.Item>
                        <Descriptions.Item label="Version state"><Tag color={target.version_state === 'unchanged' ? 'success' : 'warning'}>{target.version_state}</Tag></Descriptions.Item>
                        <Descriptions.Item label="Baseline hash"><Text code>{target.baseline.content_hash ?? '—'}</Text></Descriptions.Item>
                        <Descriptions.Item label="Current hash"><Text code>{target.current.content_hash ?? '—'}</Text></Descriptions.Item>
                        <Descriptions.Item label="Checked at">{target.checked_at}</Descriptions.Item>
                      </Descriptions>
                    ))}
                  </Space>
                ) : <Text type="secondary">尚未运行本次 KE-side Preflight。</Text>}
              </Card>

              {selectedCandidate.target_snapshots.length > 0 && (
                <Card size="small" title="Target snapshot / deterministic warnings">
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    {selectedCandidate.target_snapshots.map((target) => (
                      <Descriptions key={target.object_id} size="small" bordered column={1}>
                        <Descriptions.Item label="Object">{target.object_type} · <Text code>{target.object_id}</Text></Descriptions.Item>
                        <Descriptions.Item label="Version"><Tag color={target.version_state === 'unchanged' ? 'success' : 'warning'}>{target.version_state}</Tag></Descriptions.Item>
                        <Descriptions.Item label="Baseline title">{target.baseline_title ?? '—'}</Descriptions.Item>
                        <Descriptions.Item label="Current title">{target.current_title ?? '—'}</Descriptions.Item>
                        <Descriptions.Item label="Baseline excerpt">{target.baseline_excerpt ?? '—'}</Descriptions.Item>
                        <Descriptions.Item label="Current excerpt">{target.current_excerpt ?? '—'}</Descriptions.Item>
                      </Descriptions>
                    ))}
                  </Space>
                </Card>
              )}

              {policy.relationStagingOnly ? (
                <Alert
                  type="warning"
                  showIcon
                  message="relation_change = staging-only"
                  description="当前 Cognition App 没有 formal generic Relation API；因此本 candidate 只允许 Human Review，不渲染 Formalize / Preview / Apply 路径。"
                />
              ) : (
                <Card size="small" title="3–5 · Formal Integration Boundary">
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <div>
                      <Title level={5}>3 · Explicit Formalize</Title>
                      <Text type="secondary">创建 Cognition Proposal item；本步骤本身不修改正式 target。</Text>
                      {selectedCandidate.intent === 'add_evidence' && (
                        <div style={{ marginTop: 8 }}>
                          <Text strong>Evidence polarity（必须显式选择）：</Text>{' '}
                          <Radio.Group
                            value={polarity}
                            onChange={(event) => setPolarity(event.target.value as EvidenceRole)}
                            disabled={Boolean(handoff)}
                          >
                            <Radio.Button value="supporting">supporting</Radio.Button>
                            <Radio.Button value="counter">counter</Radio.Button>
                          </Radio.Group>
                        </div>
                      )}
                      <div style={{ marginTop: 8 }}>
                        <Button
                          type="primary"
                          onClick={() => void runFormalize()}
                          disabled={!policy.canFormalize}
                          loading={actionLoading === 'formalize'}
                        >
                          Formalize
                        </Button>
                        {!policy.canFormalize && !policy.formalized && (
                          <Text type="secondary" style={{ marginLeft: 8 }}>
                            {returnCandidateDisabledReason('formalize', policy)}
                          </Text>
                        )}
                        {policy.formalized && <Tag color="success" style={{ marginLeft: 8 }}>Proposal 已创建</Tag>}
                      </div>
                    </div>

                    <Divider style={{ margin: '4px 0' }} />

                    <div>
                      <Title level={5}>4 · Cognition official Preview</Title>
                      <Alert
                        type="success"
                        showIcon
                        message="zero-write Preview"
                        description="Preview 由 Cognition official API 执行；backend 会复核 official _hash。此步骤不会修改正式 Cognition target。"
                        style={{ marginBottom: 8 }}
                      />
                      <Button
                        onClick={() => void runPreview()}
                        disabled={!policy.canPreview}
                        loading={actionLoading === 'preview'}
                      >
                        运行 Cognition official Preview
                      </Button>
                      {!policy.canPreview && !policy.previewed && (
                        <Text type="secondary" style={{ marginLeft: 8 }}>
                          {returnCandidateDisabledReason('preview', policy)}
                        </Text>
                      )}
                      {handoff?.preview && (
                        <div style={{ marginTop: 10 }}>
                          <Text strong>Preview target hashes</Text>
                          <JsonBlock value={handoff.preview.target_hashes ?? {}} />
                          <Text strong>Preview response</Text>
                          <JsonBlock value={handoff.preview.response ?? handoff.preview} />
                        </div>
                      )}
                    </div>

                    <Divider style={{ margin: '4px 0' }} />

                    <div>
                      <Title level={5}>5 · Explicit Human Apply</Title>
                      <Alert
                        type="warning"
                        showIcon
                        message="Human Apply 是独立正式写动作"
                        description="必须先有当前 Preview，并显式勾选确认；backend 仍是 stale/hash race 的最终裁决者。"
                        style={{ marginBottom: 8 }}
                      />
                      <Checkbox
                        checked={applyConfirmed}
                        onChange={(event) => setApplyConfirmed(event.target.checked)}
                        disabled={policy.applied || !policy.previewed || handoffResponse?.formal_apply_supported !== true}
                      >
                        我确认执行 Cognition Human Apply（正式认知写入）
                      </Checkbox>
                      <div style={{ marginTop: 8 }}>
                        <Button
                          danger
                          type="primary"
                          onClick={runApply}
                          disabled={!policy.canApply}
                          loading={actionLoading === 'apply'}
                        >
                          Human Apply
                        </Button>
                        {!policy.canApply && !policy.applied && (
                          <Text type="secondary" style={{ marginLeft: 8 }}>
                            {returnCandidateDisabledReason('apply', policy)}
                          </Text>
                        )}
                        {policy.applied && <Tag color="success" style={{ marginLeft: 8 }}>已 Apply · 不可重复</Tag>}
                      </div>
                      {handoff?.apply && (
                        <div style={{ marginTop: 10 }}>
                          <Text strong>Apply response</Text>
                          <JsonBlock value={handoff.apply.response ?? handoff.apply} />
                          <Text strong>Formal readback</Text>
                          <JsonBlock value={handoff.apply.readback ?? null} />
                        </div>
                      )}
                    </div>
                  </Space>
                </Card>
              )}

              {handoff && (
                <Card size="small" title="Formal handoff backend state">
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text>Proposal ID：<Text code>{handoff.proposal_id}</Text></Text>
                      <Text>Item ID：<Text code>{handoff.proposal_item_id}</Text></Text>
                      <Tag>writer={handoff.writer}</Tag>
                      <Tag color={handoff.formal_write_performed ? 'success' : 'default'}>
                        formal_write_performed={String(handoff.formal_write_performed)}
                      </Tag>
                    </Space>
                    {handoff.target_identities && handoff.target_identities.length > 0 && (
                      <Descriptions size="small" bordered column={1}>
                        {handoff.target_identities.map((identity) => (
                          <Descriptions.Item key={identity.ke_target_id} label={identity.object_type}>
                            KE <Text code>{identity.ke_target_id}</Text> → Cognition UUID <Text code>{identity.cognition_target_id}</Text>
                          </Descriptions.Item>
                        ))}
                      </Descriptions>
                    )}
                  </Space>
                </Card>
              )}
            </Space>
          )}
        </Col>
      </Row>
    </Space>
  );
};

export default ReturnCandidateConsole;
