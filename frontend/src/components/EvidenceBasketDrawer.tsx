import { DeleteOutlined, ExperimentOutlined } from '@ant-design/icons';
import { Button, Drawer, Empty, List, Space, Tag, Typography } from 'antd';
import React from 'react';
import type { EvidenceRefInput } from '../api/types';

const { Text, Paragraph } = Typography;

interface Props {
  open: boolean;
  items: EvidenceRefInput[];
  onClose: () => void;
  onRemove: (chunkId: string) => void;
  onClear: () => void;
  onCreateTask: () => void;
}

const EvidenceBasketDrawer: React.FC<Props> = ({
  open,
  items,
  onClose,
  onRemove,
  onClear,
  onCreateTask,
}) => (
  <Drawer
    title={`Evidence Basket（${items.length}）`}
    placement="right"
    width={620}
    open={open}
    onClose={onClose}
    extra={
      <Space>
        <Button danger disabled={items.length === 0} onClick={onClear}>
          清空
        </Button>
        <Button
          type="primary"
          icon={<ExperimentOutlined />}
          disabled={items.length === 0}
          onClick={onCreateTask}
        >
          创建 TaskPack
        </Button>
      </Space>
    }
  >
    {items.length === 0 ? (
      <Empty description="尚未选择证据" />
    ) : (
      <List
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button
                key="remove"
                type="text"
                danger
                icon={<DeleteOutlined />}
                onClick={() => onRemove(item.chunk_id)}
              >
                移除
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={
                <Space size={6} wrap>
                  <Text strong>{item.title || item.document_id}</Text>
                  <Tag>{item.document_id}</Tag>
                  {item.evidence_level != null && <Tag>E{item.evidence_level}</Tag>}
                </Space>
              }
              description={
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  {item.heading_path && <Text type="secondary">{item.heading_path}</Text>}
                  {item.excerpt && (
                    <Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0 }}>
                      {item.excerpt}
                    </Paragraph>
                  )}
                  <Text code>{item.chunk_id}</Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    )}
  </Drawer>
);

export default EvidenceBasketDrawer;
