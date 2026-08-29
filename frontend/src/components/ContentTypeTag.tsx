import { Tag } from 'antd';
import React from 'react';

const TYPE_COLORS: Record<string, string> = {
  prose: 'default',
  table: 'purple',
  causal_chain: 'geekblue',
  code: 'green',
  comparison: 'orange',
  decision_tree: 'gold',
  monitoring: 'lime',
  reference: 'cyan',
  audit: 'red',
  summary: 'magenta',
};

const ContentTypeTag: React.FC<{ type: string }> = ({ type }) => (
  <Tag color={TYPE_COLORS[type] ?? 'default'}>{type}</Tag>
);

export default ContentTypeTag;
