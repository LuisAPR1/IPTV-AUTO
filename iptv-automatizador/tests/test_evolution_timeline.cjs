'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Timeline = require('../static/dbz/evolution-timeline.js');

test('idle holds the current form and pingpongs without duplicate endpoints', () => {
  const timeline = new Timeline(4);
  const frames = [timeline.getState().frame];
  for (let i = 0; i < 12; i += 1) frames.push(timeline.advance(700 / 6).frame);
  assert.deepEqual(frames, [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0]);
  assert.equal(timeline.getState().phase, 4);
  assert.equal(timeline.getState().mode, 'idle');
});

test('one-step progress uses 1400ms idle then all four 150ms transition frames', () => {
  const timeline = new Timeline();
  timeline.setTarget(2);
  assert.equal(timeline.advance(1399).mode, 'idle');
  assert.equal(timeline.advance(1).frame, 4);
  assert.equal(timeline.advance(150).frame, 5);
  assert.equal(timeline.advance(150).frame, 6);
  assert.equal(timeline.advance(150).frame, 7);
  const settled = timeline.advance(150);
  assert.deepEqual(settled, { phase: 2, target: 2, sheet: 1, frame: 0, mode: 'idle' });
  assert.equal(timeline.advance(10000).phase, 2);
});

test('bursts catch up through every adjacent phase with bounded dwell and constant frame speed', () => {
  const timeline = new Timeline();
  timeline.setTarget(8);
  const phases = [1];
  let elapsed = 0;
  let transitionStarted = null;
  const transitionDurations = [];
  while (timeline.getState().phase < 8 && elapsed < 10000) {
    const previous = timeline.getState();
    const state = timeline.advance(50);
    elapsed += 50;
    if (state.mode === 'forward' && previous.mode === 'idle') transitionStarted = elapsed;
    if (state.phase !== previous.phase) {
      phases.push(state.phase);
      transitionDurations.push(elapsed - transitionStarted);
    }
  }
  assert.deepEqual(phases, [1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(transitionDurations, [600, 600, 600, 600, 600, 600, 600]);
  assert.equal(elapsed, 8650); // Five 450ms holds, one 800ms and one 1400ms.
});

test('repeated progress polls neither restart idle nor interrupt a forward transition', () => {
  const timeline = new Timeline();
  timeline.setTarget(2);
  for (let i = 0; i < 14; i += 1) {
    timeline.advance(100);
    timeline.setTarget(2);
  }
  assert.equal(timeline.getState().mode, 'forward');
  for (let i = 0; i < 6; i += 1) {
    timeline.advance(100);
    timeline.setTarget(2);
  }
  assert.equal(timeline.getState().phase, 2);
  assert.equal(timeline.getState().mode, 'idle');
});

test('long stalls preserve the aura cycle and satisfy the hold before new progress', () => {
  const timeline = new Timeline(3);
  const before = timeline.advance(14000 + 700 / 6);
  assert.equal(before.frame, 1);
  timeline.setTarget(4);
  const moving = timeline.advance(0);
  assert.equal(moving.mode, 'forward');
  assert.equal(moving.frame, 4);
});

test('rollback visits every lower form using reverse transformation frames at 150ms', () => {
  const timeline = new Timeline(7);
  timeline.setTarget(1);
  const phases = [7];
  for (let high=7; high>1; high--) {
    for (const frame of [7,6,5,4]) {
      assert.equal(timeline.getState().mode, 'backward');
      assert.equal(timeline.getState().sheet, high-2);
      assert.equal(timeline.getState().frame, frame);
      timeline.advance(150);
    }
    phases.push(timeline.getState().phase);
  }
  assert.deepEqual(phases,[7,6,5,4,3,2,1]);
  assert.equal(timeline.getState().mode,'idle');
  assert.equal(timeline.advance(10000).phase,1);
});

test('rollback reverses an in-flight forward transition without jumping frames', () => {
  const timeline = new Timeline(6);
  timeline.setTarget(8);
  timeline.advance(800+310);
  const current=timeline.getState();
  const reverse=timeline.setTarget(1);
  assert.equal(reverse.mode,'backward');
  assert.equal(reverse.sheet,current.sheet);
  assert.equal(reverse.frame,current.frame);
  timeline.advance(311);
  assert.equal(timeline.getState().phase,6);
  timeline.advance(5*600);
  assert.equal(timeline.getState().phase,1);
});

test('lower target still ahead of character only discards stale backlog', () => {
  const timeline = new Timeline();
  timeline.setTarget(8); timeline.advance(500);
  const before=timeline.getState();
  timeline.setTarget(3);
  assert.equal(timeline.getState().mode,'forward');
  assert.equal(timeline.getState().frame,before.frame);
  timeline.advance(10000);
  assert.equal(timeline.getState().phase,3);
});

test('repeated polls and lower targets do not restart a reverse transition', () => {
  const timeline=new Timeline(7);timeline.setTarget(3);
  timeline.advance(300);timeline.setTarget(3);timeline.setTarget(1);
  assert.equal(timeline.getState().frame,5);
  timeline.advance(300);
  assert.equal(timeline.getState().phase,6);
  timeline.advance(3000);
  assert.equal(timeline.getState().phase,1);
});

test('updated target stops descent at the new destination without reaching stale target', () => {
  const timeline=new Timeline(7);timeline.setTarget(1);
  timeline.advance(200);timeline.setTarget(4);
  timeline.advance(1600);
  assert.equal(timeline.getState().phase,4);
  assert.equal(timeline.getState().mode,'idle');
});

test('new higher target reverses the current backward frames smoothly', () => {
  const timeline=new Timeline(7);timeline.setTarget(1);timeline.advance(210);
  const before=timeline.getState();timeline.setTarget(8);
  assert.equal(timeline.getState().mode,'forward');
  assert.equal(timeline.getState().sheet,before.sheet);
  assert.equal(timeline.getState().frame,before.frame);
  timeline.advance(211);assert.equal(timeline.getState().phase,7);
  timeline.advance(2000);assert.equal(timeline.getState().phase,8);
});

test('invalid targets and deltas do not mutate state; numeric boundaries clamp safely', () => {
  const timeline = new Timeline(4);
  const original = timeline.advance(50);
  for (const value of [NaN, Infinity, -Infinity, 'nope', '', null, undefined, {}, []]) {
    assert.deepEqual(timeline.setTarget(value), original);
  }
  for (const value of [NaN, Infinity, -Infinity, -1, '50', null]) {
    assert.deepEqual(timeline.advance(value), original);
  }
  assert.equal(timeline.setTarget(0).target, 1);
  assert.equal(timeline.setTarget(99).target, 8);
  assert.equal(new Timeline(8).getState().sheet, 7);
  assert.equal(new Timeline(NaN).getState().phase, 1);
});

test('hard reset clears old progress, rollback and aura timing for a new job', () => {
  const timeline = new Timeline(7);
  timeline.setTarget(2);
  timeline.advance(300);
  assert.deepEqual(timeline.reset(), { phase: 1, target: 1, sheet: 0, frame: 0, mode: 'idle' });
  assert.deepEqual(timeline.reset('4'), { phase: 4, target: 4, sheet: 3, frame: 0, mode: 'idle' });
  assert.deepEqual(timeline.reset(Infinity), timeline.getState());
});

test('one large advance matches incremental elapsed time and handles maximum finite delta', () => {
  const large = new Timeline();
  const incremental = new Timeline();
  large.setTarget(8);
  incremental.setTarget(8);
  large.advance(10000);
  for (let i = 0; i < 1000; i += 1) incremental.advance(10);
  assert.deepEqual(large.getState(), incremental.getState());
  large.reset();
  large.setTarget(8);
  const state = large.advance(Number.MAX_VALUE);
  assert.equal(state.phase, 8);
  assert.equal(state.mode, 'idle');
  assert.ok(Number.isFinite(state.frame));
});

test('browser global exposes the same usable constructor without CommonJS', () => {
  const context = {};
  vm.runInNewContext(fs.readFileSync(require.resolve('../static/dbz/evolution-timeline.js'), 'utf8'), context);
  assert.equal(typeof context.DBZEvolutionTimeline, 'function');
  assert.equal(new context.DBZEvolutionTimeline(5).getState().phase, 5);
});
