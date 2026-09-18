import test from 'node:test';
import assert from 'node:assert/strict';
import { inlineRuns } from '../static/js/richtext.js';
import { pendingJob, job } from '../static/js/api.js';

test('preview preserves words and nested emphasis', () => {
  const runs = inlineRuns('Use **reviewed _facts_** in your deck.');
  assert.equal(runs.map(r => r.text).join(''), 'Use reviewed facts in your deck.');
  assert.ok(runs.some(r => r.text === 'facts' && r.bold && r.italic));
});

test('preview does not turn javascript URLs into links', () => {
  assert.ok(inlineRuns('[click](javascript:alert(1))').every(r => !r.link));
});

test('completed jobs clear reload recovery state', async () => {
  const items = new Map();
  globalThis.sessionStorage = {
    getItem: k => items.get(k) || null,
    setItem: (k, v) => items.set(k, v),
    removeItem: k => items.delete(k),
  };
  const original = globalThis.fetch;
  const id = 'a'.repeat(32);
  globalThis.fetch = async path => ({ok: true, json: async () => path === '/api/plan' ? {id} : {status: 'done', result: {slides: []}}});
  try {
    const result = await job('/api/plan', {}, () => assert.equal(pendingJob().id, id));
    assert.deepEqual(result, {slides: []});
    assert.equal(pendingJob(), null);
  } finally {
    globalThis.fetch = original;
    delete globalThis.sessionStorage;
  }
});
