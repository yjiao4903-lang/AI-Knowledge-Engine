import { Button, Card, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

type Note = {
  id: string;
  chunk_id: string;
  document_id: string;
  heading_path: string | null;
  stance: string;
  body: string;
  task_id: string | null;
  updated_at: string;
};

const STANCE_COLOR: Record<string, string> = {
  agree: 'green',
  disagree: 'red',
  question: 'gold',
  mechanism: 'blue',
  note: 'default',
};

const NotesPage: React.FC = () => {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [stance, setStance] = useState<string | undefined>();
  const [notes, setNotes] = useState<Note[]>([]);

  const load = async () => {
    const params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    const res = await fetch(`/api/notes/?${params.toString()}`);
    if (!res.ok) {
      void message.error('加载笔记失败');
      return;
    }
    const data = (await res.json()) as { notes: Note[] };
    setNotes(stance ? data.notes.filter((n) => n.stance === stance) : data.notes);
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page-container">
      <Card title="个人理解记录（非正式认知）">
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索笔记正文 / chunk"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onPressEnter={() => void load()}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="立场"
            style={{ width: 140 }}
            value={stance}
            onChange={setStance}
            options={['agree', 'disagree', 'question', 'mechanism', 'note'].map((v) => ({
              value: v,
              label: v,
            }))}
          />
          <Button onClick={() => void load()}>刷新</Button>
        </Space>
        <Table
          rowKey="id"
          size="small"
          dataSource={notes}
          pagination={{ pageSize: 20 }}
          columns={[
            {
              title: '立场',
              dataIndex: 'stance',
              width: 110,
              render: (v: string) => <Tag color={STANCE_COLOR[v] ?? 'default'}>{v}</Tag>,
            },
            { title: '文档', dataIndex: 'document_id', width: 90 },
            { title: '章节', dataIndex: 'heading_path', ellipsis: true },
            { title: '笔记', dataIndex: 'body', ellipsis: true },
            {
              title: '操作',
              width: 160,
              render: (_: unknown, r: Note) => (
                <Button
                  size="small"
                  onClick={() =>
                    navigate(`/document/${encodeURIComponent(r.document_id)}?chunk=${encodeURIComponent(r.chunk_id)}`)
                  }
                >
                  打开证据
                </Button>
              ),
            },
          ]}
        />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
          这些记录只存在 KE 本地库，不会写入 Cognition，也不会自动变成 Judgment。
        </Typography.Paragraph>
      </Card>
    </div>
  );
};

export default NotesPage;
