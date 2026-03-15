/**
 * RGB Waveform Renderer — Custom Canvas-based waveform where color
 * encodes frequency content: R=bass, G=mids, B=highs.
 */

class RGBWaveformRenderer {
  constructor(canvas, audio) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.audio = audio;

    this.low = [];
    this.mid = [];
    this.high = [];
    this.sampleRate = 60;
    this.duration = 0;
    this.sections = [];

    this.pixelsPerSecond = 100;
    this.scrollOffset = 0; // in pixels
    this.isPlaying = false;
    this.autoFollow = true;

    this._resizeObserver = new ResizeObserver(() => this._handleResize());
    this._resizeObserver.observe(this.canvas.parentElement);
    this._handleResize();

    this._bindEvents();
    this._animationFrame = null;
  }

  setData(waveformData, sections) {
    this.low = waveformData.low;
    this.mid = waveformData.mid;
    this.high = waveformData.high;
    this.sampleRate = waveformData.sample_rate;
    this.duration = waveformData.duration;
    this.sections = sections || [];
    this.scrollOffset = 0;
    this.render();
  }

  startPlayback() {
    this.isPlaying = true;
    this.autoFollow = true;
    this._animate();
  }

  stopPlayback() {
    this.isPlaying = false;
    if (this._animationFrame) {
      cancelAnimationFrame(this._animationFrame);
      this._animationFrame = null;
    }
    this.render();
  }

  setZoom(pps) {
    const centerTime = (this.scrollOffset + this.canvas.width / 2) / this.pixelsPerSecond;
    this.pixelsPerSecond = Math.max(10, Math.min(500, pps));
    this.scrollOffset = Math.max(0, centerTime * this.pixelsPerSecond - this.canvas.width / 2);
    this.render();
  }

  // --- Internal ---

  _handleResize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width;
    this.canvas.height = 200;
    this.render();
  }

  _bindEvents() {
    // Horizontal scroll with mouse wheel
    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Zoom
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        this.setZoom(this.pixelsPerSecond * delta);
      } else {
        // Scroll
        this.scrollOffset = Math.max(0, this.scrollOffset + e.deltaY);
        this.autoFollow = false;
        this.render();
      }
    });

    // Click to seek
    this.canvas.addEventListener("click", (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const time = (px + this.scrollOffset) / this.pixelsPerSecond;
      if (this.audio && time >= 0 && time <= this.duration) {
        this.audio.currentTime = time;
        this.render();
      }
    });
  }

  _animate() {
    if (!this.isPlaying) return;

    if (this.autoFollow && this.audio) {
      const cursorPx = this.audio.currentTime * this.pixelsPerSecond;
      const margin = this.canvas.width * 0.3;
      if (cursorPx - this.scrollOffset > this.canvas.width - margin) {
        this.scrollOffset = cursorPx - margin;
      }
      if (cursorPx < this.scrollOffset) {
        this.scrollOffset = Math.max(0, cursorPx - margin);
      }
    }

    this.render();
    this._animationFrame = requestAnimationFrame(() => this._animate());
  }

  render() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const centerY = h / 2;

    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, w, h);

    if (this.low.length === 0) return;

    // Draw section backgrounds first
    this._renderSections(ctx, w, h);

    // Draw waveform bars
    for (let px = 0; px < w; px++) {
      const timeSec = (px + this.scrollOffset) / this.pixelsPerSecond;
      const sampleIdx = Math.floor(timeSec * this.sampleRate);
      if (sampleIdx < 0 || sampleIdx >= this.low.length) continue;

      const lo = this.low[sampleIdx];
      const mi = this.mid[sampleIdx];
      const hi = this.high[sampleIdx];

      const r = Math.floor(lo * 255);
      const g = Math.floor(mi * 255);
      const b = Math.floor(hi * 255);

      const amplitude = Math.max(lo, mi, hi);
      const barHeight = amplitude * centerY * 0.9;

      ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
      ctx.fillRect(px, centerY - barHeight, 1, barHeight * 2);
    }

    // Draw center line
    ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(w, centerY);
    ctx.stroke();

    // Draw section labels
    this._renderSectionLabels(ctx, w, h);

    // Draw cursor
    if (this.audio) {
      this._renderCursor(ctx, w, h);
    }
  }

  _renderSections(ctx, w, h) {
    const colors = {
      intro: "rgba(70, 130, 180, 0.15)",
      verse: "rgba(32, 178, 170, 0.15)",
      build: "rgba(255, 140, 0, 0.2)",
      drop: "rgba(220, 20, 60, 0.2)",
      fakeout: "rgba(147, 112, 219, 0.25)",
      breakdown: "rgba(60, 179, 113, 0.15)",
      outro: "rgba(112, 128, 144, 0.15)",
    };

    for (const sec of this.sections) {
      const x1 = sec.start * this.pixelsPerSecond - this.scrollOffset;
      const x2 = sec.end * this.pixelsPerSecond - this.scrollOffset;

      if (x2 < 0 || x1 > w) continue;

      const clampX1 = Math.max(0, x1);
      const clampX2 = Math.min(w, x2);

      ctx.fillStyle = colors[sec.label] || "rgba(128, 128, 128, 0.1)";
      ctx.fillRect(clampX1, 0, clampX2 - clampX1, h);

      // Section boundary line
      if (x1 >= 0 && x1 <= w) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x1, 0);
        ctx.lineTo(x1, h);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  _renderSectionLabels(ctx, w, h) {
    const labelColors = {
      intro: "#4682B4",
      verse: "#20B2AA",
      build: "#FF8C00",
      drop: "#DC143C",
      fakeout: "#9370DB",
      breakdown: "#3CB371",
      outro: "#708090",
    };

    ctx.font = "bold 11px monospace";
    ctx.textBaseline = "top";

    for (const sec of this.sections) {
      const x = sec.start * this.pixelsPerSecond - this.scrollOffset;
      if (x < -100 || x > w) continue;

      const label = sec.label.toUpperCase();
      const color = labelColors[sec.label] || "#888";

      // Background pill
      const textWidth = ctx.measureText(label).width;
      const px = Math.max(4, x + 4);

      ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
      ctx.beginPath();
      ctx.roundRect(px - 2, 4, textWidth + 8, 18, 3);
      ctx.fill();

      ctx.fillStyle = color;
      ctx.fillText(label, px + 2, 7);
    }
  }

  _renderCursor(ctx, w, h) {
    const cursorX = this.audio.currentTime * this.pixelsPerSecond - this.scrollOffset;
    if (cursorX < 0 || cursorX > w) return;

    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cursorX, 0);
    ctx.lineTo(cursorX, h);
    ctx.stroke();
    ctx.lineWidth = 1;
  }
}
