import React from 'react';

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * 生成查询高亮正则：按空白切词；纯 ASCII 词要求 ≥2 字符，
 * CJK 长词额外逐字拆分以支持中文子串命中。
 */
export function buildHighlightRegex(query: string): RegExp | null {
  const terms = new Set<string>();
  for (const raw of query.split(/\s+/)) {
    const term = raw.trim();
    if (!term) continue;
    if (/[\u4e00-\u9fff]/.test(term)) {
      terms.add(escapeRegExp(term));
      for (const ch of term) {
        if (/[\u4e00-\u9fff]/.test(ch)) terms.add(ch);
      }
    } else if (term.length >= 2) {
      terms.add(escapeRegExp(term));
    }
  }
  if (terms.size === 0) return null;
  return new RegExp(`(${[...terms].join('|')})`, 'gi');
}

/** 将文本按查询词切分并 <mark> 高亮 */
export const HighlightText: React.FC<{ text: string; query: string }> = ({ text, query }) => {
  const regex = buildHighlightRegex(query);
  if (!regex || !text) return <>{text}</>;
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <mark key={i}>{part}</mark> : <React.Fragment key={i}>{part}</React.Fragment>,
      )}
    </>
  );
};
