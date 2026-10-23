(function (root, factory) {
  'use strict';
  const Timeline = factory();
  if (typeof module === 'object' && module.exports) module.exports = Timeline;
  if (root) root.DBZEvolutionTimeline = Timeline;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const IDLE_FRAMES = [0, 1, 2, 3, 2, 1];
  const IDLE_CYCLE_MS = 700;
  const TRANSITION_FRAME_MS = 150;
  const TRANSITION_MS = TRANSITION_FRAME_MS * 4;
  const MAX_DWELL_MS = 1400;

  function normalizeStep(step) {
    if (typeof step !== 'number' && typeof step !== 'string') return null;
    if (typeof step === 'string' && !step.trim()) return null;
    const value = Number(step);
    return Number.isFinite(value) ? Math.max(1, Math.min(8, Math.trunc(value))) : null;
  }

  class DBZEvolutionTimeline {
    constructor(step = 1) {
      this.reset(normalizeStep(step) === null ? 1 : step);
    }

    // A new job starts immediately; reported retries use setTarget instead.
    reset(step = 1) {
      const phase = normalizeStep(step);
      if (phase === null) return this.getState();
      this.phase = phase;
      this.target = phase;
      this.mode = 'idle';
      this.idleElapsed = 0;
      this.idleCycle = 0;
      this.transitionElapsed = 0;
      return this.getState();
    }

    setTarget(step) {
      const target = normalizeStep(step);
      if (target === null || target === this.target) return this.getState();

      // Reverse the current transition in place, preserving the visible frame.
      // Each backward edge uses the lower form's transformation sheet: 7,6,5,4.
      if (this.mode === 'forward' && target <= this.phase) {
        this.phase += 1;
        this.mode = 'backward';
        this.transitionElapsed = Math.max(0, TRANSITION_MS - this.transitionElapsed - 1e-7);
      } else if (this.mode === 'backward' && target >= this.phase) {
        this.phase -= 1;
        this.mode = 'forward';
        this.transitionElapsed = Math.max(0, TRANSITION_MS - this.transitionElapsed - 1e-7);
      } else if (this.mode === 'idle' && target < this.phase) {
        this.mode = 'backward';
        this.transitionElapsed = 0;
      }

      this.target = target;
      return this.getState();
    }

    advance(ms) {
      if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) {
        return this.getState();
      }

      let remaining = ms;
      // At most seven forward transitions can occur before reaching the target.
      // Large background-tab deltas therefore cost constant, bounded work.
      while (true) {
        if (this.mode === 'idle') {
          if (this.phase === this.target) {
            this.advanceIdle(remaining);
            break;
          }

          const gap = this.target - this.phase;
          const dwell = gap < 0 ? 0 : gap >= 3 ? 450 : gap === 2 ? 800 : MAX_DWELL_MS;
          const wait = Math.max(0, dwell - this.idleElapsed);
          if (remaining < wait) {
            this.advanceIdle(remaining);
            break;
          }

          this.advanceIdle(wait);
          remaining -= wait;
          this.mode = gap < 0 ? 'backward' : 'forward';
          this.transitionElapsed = 0;
        }

        const wait = TRANSITION_MS - this.transitionElapsed;
        if (remaining < wait) {
          this.transitionElapsed += remaining;
          break;
        }

        remaining -= wait;
        this.phase += this.mode === 'forward' ? 1 : -1;
        this.mode = 'idle';
        this.transitionElapsed = 0;
        this.idleElapsed = 0;
        this.idleCycle = 0;
        }

      return this.getState();
    }

    advanceIdle(ms) {
      this.idleElapsed = Math.min(MAX_DWELL_MS, this.idleElapsed + ms);
      // Reduce before adding so even very large finite deltas remain finite.
      this.idleCycle = (this.idleCycle + ms % IDLE_CYCLE_MS) % IDLE_CYCLE_MS;
    }

    getState() {
      const state = {
        phase: this.phase,
        target: this.target,
        sheet: this.phase - 1,
        frame: 0,
        mode: this.mode
      };

      if (this.mode === 'idle') {
        const index = Math.floor(this.idleCycle / IDLE_CYCLE_MS * IDLE_FRAMES.length + 1e-10);
        state.frame = IDLE_FRAMES[index % IDLE_FRAMES.length];
      } else if (this.mode === 'forward') {
        state.frame = 4 + Math.min(3, Math.floor(this.transitionElapsed / TRANSITION_FRAME_MS));
      } else if (this.mode === 'backward') {
        state.sheet = this.phase - 2;
        state.frame = 7 - Math.min(3, Math.floor(this.transitionElapsed / TRANSITION_FRAME_MS));
      }

      return state;
    }
  }

  return DBZEvolutionTimeline;
});
