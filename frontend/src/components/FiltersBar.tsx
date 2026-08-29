import { Col, Row, Select } from 'antd';
import React from 'react';
import type { DocumentInfo, SearchFilters } from '../api/types';

const CONTENT_TYPES = [
  'prose',
  'table',
  'causal_chain',
  'code',
  'comparison',
  'decision_tree',
  'monitoring',
  'reference',
  'audit',
  'summary',
];

const EVIDENCE_OPTIONS = [1, 2, 3, 4, 5].map((n) => ({
  value: n,
  label: `L${n}`,
}));

export interface FiltersValue extends SearchFilters {
  domain?: string[];
}

const FiltersBar: React.FC<{
  documents: DocumentInfo[];
  value: FiltersValue;
  onChange: (v: FiltersValue) => void;
}> = ({ documents, value, onChange }) => {
  const domains = [...new Set(documents.map((d) => d.domain).filter(Boolean))].sort();

  return (
    <Row gutter={12}>
      <Col span={6}>
        <Select
          mode="multiple"
          allowClear
          placeholder="Domain"
          style={{ width: '100%' }}
          value={value.domain ?? []}
          options={domains.map((d) => ({ value: d, label: d }))}
          onChange={(domain) => {
            // Domain 不是后端过滤字段：据此联动勾选对应文档
            const docIds = domain.length
              ? documents.filter((d) => domain.includes(d.domain)).map((d) => d.id)
              : [];
            onChange({ ...value, domain, document_ids: docIds });
          }}
        />
      </Col>
      <Col span={4}>
        <Select
          mode="multiple"
          allowClear
          placeholder="Evidence (L1-L5)"
          style={{ width: '100%' }}
          value={value.evidence_levels ?? []}
          options={EVIDENCE_OPTIONS}
          onChange={(evidence_levels) => onChange({ ...value, evidence_levels })}
        />
      </Col>
      <Col span={6}>
        <Select
          mode="multiple"
          allowClear
          placeholder="Content Type"
          style={{ width: '100%' }}
          value={value.content_types ?? []}
          options={CONTENT_TYPES.map((t) => ({ value: t, label: t }))}
          onChange={(content_types) => onChange({ ...value, content_types })}
        />
      </Col>
      <Col span={8}>
        <Select
          mode="multiple"
          allowClear
          showSearch
          placeholder="Document（名称 / 代号）"
          style={{ width: '100%' }}
          value={value.document_ids ?? []}
          optionFilterProp="label"
          options={documents.map((d) => ({
            value: d.id,
            label: `${d.id} · ${d.title}`,
          }))}
          onChange={(document_ids) => onChange({ ...value, document_ids })}
        />
      </Col>
    </Row>
  );
};

export default FiltersBar;
