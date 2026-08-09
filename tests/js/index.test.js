import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const HTML = readFileSync(new URL('../../static/index.html', import.meta.url), 'utf-8');

function loadPage() {
  const dom = new JSDOM(HTML, { runScripts: 'dangerously', url: 'http://localhost:5000' });
  return dom.window;
}

/** Attach a story file the way the browser does: set files, dispatch change. */
async function attachStory(win, name = 'sforzato.txt', body = 'The fleet dropped out.') {
  const input = win.document.getElementById('story_file');
  const file = new win.File([body], name, { type: 'text/plain' });
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  input.dispatchEvent(new win.Event('change', { bubbles: true }));
  // FileReader is async; let its load event settle.
  await vi.waitFor(() =>
    expect(win.document.getElementById('story_name').textContent).toBe(name));
}

describe('story upload controls', () => {
  it('hides the rewrite controls until a story is attached', () => {
    const win = loadPage();
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls).not.toBeNull();
    expect(controls.hidden || controls.style.display === 'none').toBe(true);
  });

  it('reveals the mode radios and notes box once a story is attached', async () => {
    const win = loadPage();
    await attachStory(win);
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls.hidden || controls.style.display === 'none').toBe(false);
    expect(win.document.querySelector('input[name="rewrite_mode"]:checked').value)
      .toBe('reimagine');
    expect(win.document.getElementById('rewrite_notes')).not.toBeNull();
  });

  it('blanks target length and audience when a story is attached', async () => {
    const win = loadPage();
    expect(win.document.getElementById('target_length').value).toBe('8,000 words');
    expect(win.document.getElementById('target_length').required).toBe(true);
    expect(win.document.getElementById('target_audience').required).toBe(true);
    await attachStory(win);
    expect(win.document.getElementById('target_length').value).toBe('');
    expect(win.document.getElementById('target_audience').value).toBe('');
    expect(win.document.getElementById('target_length').required).toBe(false);
    expect(win.document.getElementById('target_audience').required).toBe(false);
    expect(win.document.getElementById('target_length').placeholder)
      .toBe('blank = match the original');
  });

  it('restores the defaults when the story is removed', async () => {
    const win = loadPage();
    await attachStory(win);
    win.document.getElementById('story_remove').click();
    expect(win.document.getElementById('target_length').value).toBe('8,000 words');
    expect(win.document.getElementById('target_audience').value).toBe('Adult sci-fi readers');
    expect(win.document.getElementById('target_length').required).toBe(true);
    expect(win.document.getElementById('target_length').placeholder).toBe('');
    const controls = win.document.getElementById('rewrite_controls');
    expect(controls.hidden || controls.style.display === 'none').toBe(true);
  });
});

describe('run payload', () => {
  let win;
  let sent;

  beforeEach(async () => {
    win = loadPage();
    sent = null;
    win.fetch = vi.fn(async (url, opts) => {
      sent = { url, body: JSON.parse(opts.body) };
      return {
        ok: true,
        json: async () => ({
          story: 'a story', log: [], intake_brief: '=== STORY BRIEF ===',
          rewrite_mode: 'revise', title: 'The Sforzato', target_length: '8432 words',
        }),
      };
    });
  });

  it('sends story_file, rewrite_mode, and rewrite_notes', async () => {
    await attachStory(win);
    win.document.querySelector('input[name="rewrite_mode"][value="revise"]').click();
    win.document.getElementById('rewrite_notes').value = 'darker ending';
    win.document.getElementById('run-btn').click();
    await vi.waitFor(() => expect(sent).not.toBeNull());

    expect(sent.url).toContain('/run');
    expect(sent.body.story_file.filename).toBe('sforzato.txt');
    expect(sent.body.story_file.data).toContain('base64,');
    expect(sent.body.rewrite_mode).toBe('revise');
    expect(sent.body.rewrite_notes).toBe('darker ending');
  });

  it('omits story_file on a fresh run', async () => {
    win.document.getElementById('title').value = 'A Fresh Title';
    win.document.getElementById('author').value = 'A. Writer';
    win.document.getElementById('idea').value = 'a fresh idea';
    win.document.getElementById('run-btn').click();
    await vi.waitFor(() => expect(sent).not.toBeNull());
    expect(sent.body.story_file).toBeFalsy();
    expect(sent.body.rewrite_notes).toBe('');
  });

  it('renders the brief and backfills the title from the response', async () => {
    await attachStory(win);
    win.document.getElementById('run-btn').click();
    await vi.waitFor(() =>
      expect(win.document.getElementById('title').value).toBe('The Sforzato'));
    expect(win.document.body.textContent).toContain('STORY BRIEF');
  });
});
