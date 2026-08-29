import { Tag } from 'antd';
import React from 'react';

const EVIDENCE_COLORS: Record<number, string> = {
  1: 'volcano',
  2: 'orange',
  3: 'gold',
  4: 'cyan',
  5: 'geekblue',
};

const EVIDENCE_LABELS: Record<number, string> = {
  1: 'L1 表格/结构化',
  2: 'L2 因果链',
  3: 'L3 引用数据',
  4: 'L4 归纳观点',
  5: 'L5 展望/推测',
};

/** 证据等级徽章；evidence_level 为 null 时显示 unmarked */
const EvidenceTag: React.FC<{ level: number | null | undefined }> = ({ level }) => {
  if (level == null) {
    return <Tag>unmarked</Tag>;
  }
  return (
    <Tag color={EVIDENCE_COLORS[level] ?? 'default'}>
      {EVIDENCE_LABELS[level] ?? `L${level}`}
    </Tag>
  );
};

export default EvidenceTag;
