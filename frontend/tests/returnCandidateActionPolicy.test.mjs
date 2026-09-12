import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { getReturnCandidateActionPolicy } from '../src/features/returnCandidates/actionPolicy.js';

const clean = {
  ke_preflight_only: true,
  has_version_conflict: false,
  version_check_incomplete: false,
};

function policy(overrides = {}) {
  return getReturnCandidateActionPolicy({
    status: 'accepted',
    intent: 'revise_judgment',
    preflight: clean,
    handoff: null,
    polarity: null,
    formalApplySupported: true,
    formalWritePerformed: false,
    serverConflict: false,
    applyConfirmed: false,
    ...overrides,
  });
}

test('accepted + clean preflight enables Formalize only', () => {
  const value = policy();
  assert.equal(value.canFormalize, true);
  assert.equal(value.canPreview, false);
  assert.equal(value.canApply, false);
});

test('proposed candidate cannot enter formal path', () => {
  const value = policy({ status: 'proposed' });
  assert.equal(value.canFormalize, false);
  assert.equal(value.canPreview, false);
  assert.equal(value.canApply, false);
});

test('add_evidence requires explicit polarity', () => {
  assert.equal(policy({ intent: 'add_evidence' }).canFormalize, false);
  assert.equal(policy({ intent: 'add_evidence', polarity: 'supporting' }).canFormalize, true);
  assert.equal(policy({ intent: 'add_evidence', polarity: 'counter' }).canFormalize, true);
});

test('stale/version conflict blocks every formal action', () => {
  const stale = policy({
    preflight: { ...clean, has_version_conflict: true },
    handoff: { preview: { response: {} } },
    applyConfirmed: true,
  });
  assert.equal(stale.canFormalize, false);
  assert.equal(stale.canPreview, false);
  assert.equal(stale.canApply, false);
});

test('relation_change remains staging-only', () => {
  const value = policy({
    intent: 'relation_change',
    handoff: { preview: { response: {} } },
    applyConfirmed: true,
  });
  assert.equal(value.relationStagingOnly, true);
  assert.equal(value.canFormalize, false);
  assert.equal(value.canPreview, false);
  assert.equal(value.canApply, false);
});

test('preview requires formalization and apply requires preview + explicit confirmation', () => {
  assert.equal(policy({ handoff: {} }).canPreview, true);
  assert.equal(policy({ handoff: {}, applyConfirmed: true }).canApply, false);
  assert.equal(policy({ handoff: { preview: { response: {} } }, applyConfirmed: false }).canApply, false);
  assert.equal(policy({ handoff: { preview: { response: {} } }, applyConfirmed: true }).canApply, true);
});

test('already applied is permanently non-actionable', () => {
  const value = policy({
    handoff: { preview: { response: {} }, apply: { readback: {} } },
    applyConfirmed: true,
    formalWritePerformed: true,
  });
  assert.equal(value.applied, true);
  assert.equal(value.canFormalize, false);
  assert.equal(value.canPreview, false);
  assert.equal(value.canApply, false);
});

test('server-side 409 conflict locks formal actions until explicit refresh/re-review', () => {
  const value = policy({
    handoff: { preview: { response: {} } },
    applyConfirmed: true,
    serverConflict: true,
  });
  assert.equal(value.canPreview, false);
  assert.equal(value.canApply, false);
});

test('deterministic UI evidence exposes the required lifecycle labels', async () => {
  const source = await readFile(new URL('../src/features/returnCandidates/ReturnCandidateConsole.tsx', import.meta.url), 'utf8');
  for (const label of [
    'KE-side Preflight',
    'Cognition official Preview',
    'zero-write',
    'Human Apply',
    'staging-only',
    'supporting',
    'counter',
    'readback',
    'Backend error',
    '刷新 target version',
  ]) {
    assert.match(source, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('existing Task Center remains rendered unchanged under the DL-06D wrapper', async () => {
  const wrapper = await readFile(new URL('../src/pages/TaskCenterWithReturnReviewPage.tsx', import.meta.url), 'utf8');
  assert.match(wrapper, /<TaskCenterPage \/>/);
  assert.match(wrapper, /<ReturnCandidateConsole taskId=\{taskId\} \/>/);
});
