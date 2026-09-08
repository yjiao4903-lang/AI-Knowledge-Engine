import { Button, Input, Modal, Select, Space, message } from 'antd';
import React, { useState } from 'react';
import { api } from '../api/client';
import type { SearchResult } from '../api/types';

const STANCES = [
  { value: 'note', label: '笔记' },
  { value: 'agree', label: '同意' },
  { value: 'disagree', label: '反驳' },
  { value: 'question', label: '疑问' },
  { value: 'mechanism', label: '机制' },
];

const NoteButton: React.FC<{ result: SearchResult }> = ({ result }) => {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState('');
  const [stance, setStance] = useState('note');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const text = body.trim();
    if (!text) {
      void message.warning('请填写理解记录');
      return;
    }
    setSaving(true);
    try {
      await api.createNote({
        chunk_id: result.chunk_id,
        document_id: result.document_id,
        heading_path: result.heading_path,
        stance,
        body: text,
      });
      void message.success('已保存到理解记录（非正式认知）');
      setOpen(false);
      setBody('');
      setStance('note');
    } catch (error) {
      void message.error(`保存失败：${(error as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>
        记笔记
      </Button>
      <Modal
        title="个人理解记录"
        open={open}
        onOk={() => void save()}
        onCancel={() => setOpen(false)}
        confirmLoading={saving}
        okText="保存"
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Select value={stance} onChange={setStance} options={STANCES} style={{ width: '100%' }} />
          <Input.TextArea
            rows={5}
            maxLength={4000}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="用自己的话写下机制、反证或疑问。不会写入正式 Cognition。"
          />
        </Space>
      </Modal>
    </>
  );
};

export default NoteButton;
