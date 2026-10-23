'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Timeline = require('../static/dbz/evolution-timeline.js');

function createHarness(options = {}) {
  let nextId = 1;
  let now = 0;
  const frames = new Map();
  const timers = new Map();
  const images = [];
  const draws = [];
  const listeners = {};
  const media = { matches: !!options.reduced };
  const context = {
    globalAlpha: 1,
    clearRect() { draws.push({ clear: true }); },
    drawImage(image, ...args) { draws.push({ image, args, alpha: this.globalAlpha }); }
  };
  const canvas = {
    dataset: { assetBase: '/static/dbz/' },
    getContext() { return options.noContext ? null : context; }
  };
  const container = { hidden: true };
  const document = {
    hidden: false,
    addEventListener(event, callback) { listeners[event] = callback; }
  };
  class MockImage {
    constructor() {
      this.naturalWidth = 2048;
      this.naturalHeight = 1024;
      images.push(this);
    }
  }
  const root = {
    DBZEvolutionTimeline: Timeline,
    matchMedia() { return media; },
    requestAnimationFrame(callback) { const id = nextId++; frames.set(id, callback); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
    setTimeout(callback, delay) { const id = nextId++; timers.set(id, { callback, delay }); return id; },
    clearTimeout(id) { timers.delete(id); }
  };
  vm.runInNewContext(fs.readFileSync(require.resolve('../static/dbz/evolution-player.js'), 'utf8'), {
    window: root, document, Image: MockImage
  });
  const player = new root.DBZEvolutionPlayer(canvas, container);
  return {
    player, context, container, document, frames, timers, images, draws, media,
    get now() { return now; },
    async ready() {
      player.start();
      images.forEach(image => image.onload());
      await player.loading;
    },
    frame(delta = 0) {
      now += delta;
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach(callback => callback(now));
    },
    advance(duration, interval = 50) {
      let remaining = duration;
      while (remaining > 0) {
        const delta = Math.min(interval, remaining);
        this.frame(delta);
        remaining -= delta;
      }
    },
    visibility(hidden) {
      document.hidden = hidden;
      listeners.visibilitychange();
    }
  };
}

test('loads eight sheets, draws correct frame rectangles, and schedules only one RAF', async () => {
  const h = createHarness();
  await h.ready();
  assert.equal(h.images.length, 8);
  assert.equal(h.images[7].src, '/static/dbz/phase-8.webp?v=1');
  assert.equal(h.container.hidden, false);
  assert.equal(h.timers.size, 0);
  h.player.schedule();
  h.player.schedule();
  assert.equal(h.frames.size, 1);
  h.frame();
  h.advance(250);
  let draw = h.draws.at(-1);
  assert.equal(draw.image, h.images[0]);
  assert.deepEqual(draw.args, [1024, 0, 512, 512, 0, 0, 512, 512]);
  h.player.setStep(2);
  h.advance(1150);
  draw = h.draws.at(-1);
  assert.deepEqual(draw.args, [0, 512, 512, 512, 0, 0, 512, 512]);
  assert.equal(h.context.globalAlpha, 1);
});

test('asset errors and invalid dimensions hide decoration and never block finish', async () => {
  for (const failure of ['error', 'dimensions']) {
    const h = createHarness();
    h.player.start();
    if (failure === 'error') h.images[0].onerror();
    else {
      h.images[0].naturalWidth = 4096;
      h.images[0].onload();
    }
    await h.player.loading;
    assert.equal(h.player.failed, true);
    assert.equal(h.container.hidden, true);
    assert.equal(h.frames.size, 0);
    let completed = 0;
    h.player.finish(() => completed++);
    assert.equal(completed, 1);
    assert.equal(h.player.active, false);
  }
});

test('asset timeout has a ten-second bound and finish before load does not wait', async () => {
  const h = createHarness();
  h.player.start();
  assert.ok([...h.timers.values()].every(timer => timer.delay === 10000));
  [...h.timers.values()].forEach(timer => timer.callback());
  await h.player.loading;
  assert.equal(h.player.failed, true);
  assert.equal(h.container.hidden, true);
  let completed = 0;
  h.player.finish(() => completed++);
  assert.equal(completed, 1);

  const pending = createHarness();
  pending.player.start();
  pending.player.finish(() => completed++);
  assert.equal(completed, 2);
  assert.equal(pending.player.active, false);
});

test('missing canvas context keeps finish functional', () => {
  const h = createHarness({ noContext: true });
  h.player.start();
  assert.equal(h.images.length, 0);
  assert.equal(h.container.hidden, true);
  let completed = 0;
  h.player.finish(() => completed++);
  assert.equal(completed, 1);
});

test('async loading completed after stop cannot reopen or restart animation', async () => {
  const h = createHarness();
  h.player.start();
  h.player.stop();
  h.images.forEach(image => image.onload());
  await h.player.loading;
  assert.equal(h.player.ready, true);
  assert.equal(h.player.active, false);
  assert.equal(h.container.hidden, true);
  assert.equal(h.frames.size, 0);
  assert.equal(h.draws.length, 0);
  h.player.start();
  assert.equal(h.container.hidden, false);
  assert.equal(h.frames.size, 1);
});

test('starting a new job resets progress and cancels the old finish callback', async () => {
  const h = createHarness();
  await h.ready();
  h.frame();
  h.player.setStep(7);
  h.advance(3000);
  let completed = 0;
  h.player.finish(() => completed++);
  h.player.start();
  assert.equal(h.player.timeline.getState().phase, 1);
  assert.equal(h.player.timeline.getState().target, 1);
  h.frame();
  h.advance(15000);
  assert.equal(completed, 0);
  assert.equal(h.player.timeline.getState().phase, 1);
});

test('finish reaches phase 8 and waits a full 900ms after showing it, invoking callback once', async () => {
  const h = createHarness();
  await h.ready();
  h.frame();
  let completed = 0;
  h.player.finish(() => completed++);
  while (h.player.timeline.getState().phase !== 8) {
    h.frame(50);
    assert.ok(h.now < 10000);
  }
  assert.equal(h.player.timeline.getState().mode, 'idle');
  assert.equal(completed, 0);
  h.advance(899);
  assert.equal(completed, 0, '900ms hold starts when the final form is first displayed');
  h.advance(1);
  assert.equal(completed, 1);
  h.advance(5000);
  h.player.finishNow();
  assert.equal(completed, 1);
  assert.equal(h.frames.size, 0);
});

test('completed progress stays visible in phase 8 with a continuous pingpong aura', async () => {
  const h = createHarness();
  await h.ready();
  h.frame();
  h.player.setStep(8);
  h.advance(12000);
  assert.equal(h.player.timeline.getState().phase, 8);
  assert.equal(h.player.timeline.getState().mode, 'idle');
  const seen = new Set();
  for (let i=0; i<40; i++) {
    h.advance(50);
    const state = h.player.timeline.getState();
    assert.equal(state.phase, 8);
    seen.add(state.frame);
  }
  assert.deepEqual([...seen].sort(), [0,1,2,3]);
  assert.equal(h.player.active, true);
  assert.equal(h.container.hidden, false);
  h.player.start();
  assert.equal(h.player.timeline.getState().phase, 1);
});

test('reduced motion holds a still frame per phase without aura or crossfade flicker', async () => {
  const h = createHarness({ reduced: true });
  await h.ready();
  h.frame();
  const initialDrawCount = h.draws.length;
  h.advance(3000);
  assert.equal(h.draws.length, initialDrawCount);
  h.player.setStep(2);
  h.advance(650);
  assert.equal(h.player.timeline.getState().phase, 2);
  let draw = h.draws.at(-1);
  assert.equal(draw.image, h.images[1]);
  assert.deepEqual(draw.args.slice(0, 4), [0, 0, 512, 512]);
  h.player.setStep(1);
  h.advance(600);
  draw = h.draws.at(-1);
  assert.equal(draw.image, h.images[0]);
  assert.equal(draw.alpha, 1);
});

test('hidden tabs freeze progress and resume without consuming hidden elapsed time', async () => {
  const h = createHarness();
  await h.ready();
  h.frame();
  h.player.setStep(8);
  h.advance(500);
  const before = h.player.timeline.getState();
  h.visibility(true);
  assert.equal(h.frames.size, 0);
  h.frame(60000);
  assert.deepEqual(h.player.timeline.getState(), before);
  h.visibility(false);
  assert.equal(h.frames.size, 1);
  h.frame();
  assert.deepEqual(h.player.timeline.getState(), before);
  h.frame(50);
  assert.equal(h.player.timeline.transitionElapsed, 100);
});

test('rollback renderer plays reversed frames through all lower forms without crossfade', async () => {
  const h=createHarness();await h.ready();h.player.timeline.reset(7);h.frame();
  h.player.setStep(1);
  for(let sheet=5;sheet>=0;sheet--) {
    h.frame(0);
    for(const frame of [7,6,5,4]) {
      const draw=h.draws.at(-1);
      assert.equal(draw.image,h.images[sheet]);
      assert.equal(draw.alpha,1);
      assert.deepEqual(draw.args.slice(0,4),[(frame%4)*512,512,512,512]);
      h.advance(150);
    }
  }
  assert.equal(h.player.timeline.getState().phase,1);
  assert.equal(h.player.timeline.getState().mode,'idle');
  assert.equal(h.draws.at(-1).image,h.images[0]);
});
