/* Small decorative progress character. The real progress UI never waits for assets. */
(function (root) {
    'use strict';
    class DBZEvolutionPlayer {
        constructor(canvas, container) {
            this.canvas = canvas;
            this.container = container;
            this.context = canvas.getContext('2d');
            this.timeline = new root.DBZEvolutionTimeline();
            this.images = [];
            this.active = false;
            this.ready = false;
            this.failed = !this.context;
            this.raf = null;
            this.last = null;
            this.lastPaint = '';
            this.finishCallback = null;
            this.finishHold = 0;
            this.reducedMotion = root.matchMedia('(prefers-reduced-motion: reduce)');
            this.tick = this.tick.bind(this);
            document.addEventListener('visibilitychange', () => {
                this.last = null;
                if (document.hidden) {
                    root.cancelAnimationFrame(this.raf);
                    this.raf = null;
                } else this.schedule();
            });
        }

        load() {
            if (this.loading || this.failed) return;
            const base = this.canvas.dataset.assetBase;
            this.loading = Promise.all(Array.from({length: 8}, (_, i) => new Promise((resolve, reject) => {
                const image = new Image();
                const timeout = root.setTimeout(() => reject(new Error('Sprite load timeout')), 10000);
                image.onload = () => {
                    root.clearTimeout(timeout);
                    if (image.naturalWidth !== 2048 || image.naturalHeight !== 1024) {
                        reject(new Error('Invalid sprite dimensions'));
                    } else resolve(image);
                };
                image.onerror = () => { root.clearTimeout(timeout); reject(new Error('Sprite unavailable')); };
                image.src = `${base}phase-${i+1}.webp?v=1`;
            }))).then(images => {
                this.images = images;
                this.ready = true;
                if (this.active) {
                    this.container.hidden = false;
                    this.paint(this.timeline.getState());
                    this.schedule();
                }
            }).catch(() => {
                // Optional decoration must never block generation, retry or results.
                this.failed = true;
                this.container.hidden = true;
                this.finishNow();
            });
        }

        start(reset = true) {
            this.stop();
            if (reset) this.timeline.reset(1);
            this.active = true;
            this.lastPaint = '';
            this.container.hidden = !this.ready || this.failed;
            this.load();
            if (this.ready && !this.failed) this.paint(this.timeline.getState());
            this.schedule();
        }

        setStep(step) { this.timeline.setTarget(step); }

        stop() {
            this.active = false;
            this.last = null;
            this.finishCallback = null;
            this.finishHold = 0;
            root.cancelAnimationFrame(this.raf);
            this.raf = null;
        }

        finish(callback) {
            this.timeline.setTarget(8);
            this.finishCallback = callback;
            this.finishHold = 0;
            // A very fast job or unavailable artwork must not keep a completed UI open.
            if (!this.ready || this.failed || !this.active) this.finishNow();
        }

        finishNow() {
            const callback = this.finishCallback;
            this.stop();
            if (callback) callback();
        }

        schedule() {
            if (this.active && this.ready && !this.failed && !document.hidden && this.raf === null) {
                this.raf = root.requestAnimationFrame(this.tick);
            }
        }

        tick(now) {
            this.raf = null;
            if (!this.active || document.hidden) { this.last = null; return; }
            // Hidden tabs and slow frames cannot fast-forward through several transformations.
            const dt = this.last === null ? 0 : Math.min(100, Math.max(0, now-this.last));
            this.last = now;
            const previous = this.timeline.getState();
            this.timeline.advance(dt);
            const state = this.timeline.getState();
            this.paint(state);
            if (this.finishCallback && state.phase === 8 && state.mode === 'idle') {
                if (previous.phase === 8 && previous.mode === 'idle') this.finishHold += dt;
                if (this.finishHold >= 900) { this.finishNow(); return; }
            } else this.finishHold = 0;
            this.schedule();
        }

        paint(state) {
            const reduced = this.reducedMotion.matches;
            const key = reduced ? `still-${state.phase}` :
                `${state.mode}-${state.sheet}-${state.frame}-${state.blend ?? ''}`;
            if (key === this.lastPaint) return;
            this.lastPaint = key;
            const ctx = this.context;
            ctx.clearRect(0, 0, 512, 512);
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = 'high';
            const draw = (sheet, frame, opacity = 1) => {
                ctx.globalAlpha = opacity;
                ctx.drawImage(this.images[sheet], (frame%4)*512, Math.floor(frame/4)*512,
                    512, 512, 0, 0, 512, 512);
            };
            if (reduced) draw(state.phase-1, 0);
            else draw(state.sheet, state.frame);
            ctx.globalAlpha = 1;
        }
    }
    root.DBZEvolutionPlayer = DBZEvolutionPlayer;
})(window);
