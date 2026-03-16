/**
 * Pioneer Link — WebSocket client for real-time deck data.
 *
 * Connects to /ws/pioneer, receives deck state updates from
 * beat-link-trigger (via OSC -> Python -> WebSocket), and updates
 * the live deck panels in the UI.
 *
 * Connection status reflects actual Pioneer hardware data flow,
 * NOT the WebSocket connection to our own server.
 */

class PioneerLink {
  constructor() {
    this.ws = null;
    this.decks = { 1: {}, 2: {} };
    this.wsConnected = false;       // WebSocket to Python server
    this.pioneerLive = false;       // Actual Pioneer data flowing
    this.activeChannels = [];
    this.reconnectDelay = 2000;
    this._hasReceivedData = false;

    this.connect();
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${proto}//${location.host}/ws/pioneer`);

    this.ws.onopen = () => {
      this.wsConnected = true;
      // Don't show "Connected" yet — wait for actual Pioneer data
      this._updateConnectionStatus();
      console.log("[Pioneer] WebSocket to server open");
    };

    this.ws.onclose = () => {
      this.wsConnected = false;
      this.pioneerLive = false;
      this._updateConnectionStatus();
      console.log("[Pioneer] WebSocket closed, reconnecting...");
      setTimeout(() => this.connect(), this.reconnectDelay);
    };

    this.ws.onerror = () => {
      this.ws.close();
    };

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "full_state") {
        for (const [ch, state] of Object.entries(msg.decks)) {
          this.decks[ch] = state;
          this._updateDeckUI(parseInt(ch), state);
        }
        this._updateRawDataPanel();

      } else if (msg.type === "deck_update") {
        this.decks[msg.channel] = msg.data;
        this._updateDeckUI(msg.channel, msg.data);
        this._updateRawDataPanel();

      } else if (msg.type === "pioneer_status") {
        // This is the real Pioneer hardware status
        this.pioneerLive = msg.is_receiving;
        this.activeChannels = msg.active_channels || [];
        this._updateConnectionStatus();
      }
    };

    // Keep-alive ping every 30s
    if (this._pingInterval) clearInterval(this._pingInterval);
    this._pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send("ping");
      }
    }, 30000);
  }

  _updateConnectionStatus() {
    const el = document.getElementById("pioneer-status");
    const badge = document.getElementById("link-badge");

    if (!this.wsConnected) {
      // Server is down
      el.textContent = "Server Offline";
      el.className = "pioneer-status disconnected";
      badge.className = "heading-badge";
    } else if (this.pioneerLive) {
      // Getting actual Pioneer data
      const chList = this.activeChannels.length > 0
        ? ` (CH ${this.activeChannels.join(", ")})`
        : "";
      el.textContent = `Pioneer: Live${chList}`;
      el.className = "pioneer-status connected";
      badge.className = "heading-badge active";
    } else {
      // Server is up but no Pioneer data
      el.textContent = "Pioneer: No Data";
      el.className = "pioneer-status waiting";
      badge.className = "heading-badge";
    }
  }

  _updateDeckUI(ch, state) {
    const hasData = state.last_update > 0;
    if (hasData) this._hasReceivedData = true;

    const panel = document.getElementById(`deck-${ch}`);
    if (!panel) return;

    // Play state
    const stateEl = document.getElementById(`deck-${ch}-state`);
    if (state.is_playing) {
      stateEl.textContent = "PLAYING";
      stateEl.className = "deck-play-state playing";
      panel.classList.add("active");
    } else {
      stateEl.textContent = "STOPPED";
      stateEl.className = "deck-play-state stopped";
      panel.classList.remove("active");
    }

    // Track info
    const artist = state.track_artist || "\u2014";
    const title = state.track_title || "No track loaded";
    document.getElementById(`deck-${ch}-artist`).textContent = artist;
    document.getElementById(`deck-${ch}-title`).textContent = title;

    // BPM
    document.getElementById(`deck-${ch}-original-bpm`).textContent =
      state.original_bpm > 0 ? state.original_bpm.toFixed(1) : "\u2014";
    document.getElementById(`deck-${ch}-effective-bpm`).textContent =
      state.effective_bpm > 0 ? state.effective_bpm.toFixed(2) : "\u2014";

    // Pitch
    const pitchSign = state.pitch_percent >= 0 ? "+" : "";
    document.getElementById(`deck-${ch}-pitch`).textContent =
      state.original_bpm > 0 ? `${pitchSign}${state.pitch_percent.toFixed(2)}%` : "\u2014";

    // Position
    document.getElementById(`deck-${ch}-position`).textContent =
      state.playback_position_ms > 0
        ? this._formatMs(state.playback_position_ms)
        : "0:00.0";

    // Track length
    document.getElementById(`deck-${ch}-length`).textContent =
      state.track_length_sec > 0
        ? this._formatSec(state.track_length_sec)
        : "0:00";

    // Beat
    document.getElementById(`deck-${ch}-beat`).textContent =
      state.beat_number > 0 ? state.beat_number : "\u2014";

    // Beat within bar dots
    const dots = document.querySelectorAll(`#deck-${ch}-bar-dots .beat-dot`);
    dots.forEach((dot, i) => {
      dot.classList.toggle("active", i < state.beat_within_bar);
    });

    // Flags
    this._setFlag(`deck-${ch}-flag-onair`, state.is_on_air);
    this._setFlag(`deck-${ch}-flag-master`, state.is_master);
    this._setFlag(`deck-${ch}-flag-sync`, state.is_synced);
    this._setFlag(`deck-${ch}-flag-loop`, state.is_looping);

    // Key & genre
    document.getElementById(`deck-${ch}-key`).textContent = state.track_key || "\u2014";
    document.getElementById(`deck-${ch}-genre`).textContent = state.track_genre || "\u2014";
  }

  _updateRawDataPanel() {
    const grid = document.getElementById("pioneer-data-grid");
    if (!this._hasReceivedData) return;

    let html = "";
    for (const ch of [1, 2]) {
      const d = this.decks[ch];
      if (!d || !d.last_update) continue;

      html += `<div class="pioneer-raw-deck">
        <div class="raw-deck-header">Channel ${ch}</div>
        <table class="raw-data-table">
          <tr><td>Playing</td><td>${d.is_playing ? "YES" : "NO"}</td></tr>
          <tr><td>On Air</td><td>${d.is_on_air ? "YES" : "NO"}</td></tr>
          <tr><td>Original BPM</td><td>${d.original_bpm > 0 ? d.original_bpm.toFixed(2) : "\u2014"}</td></tr>
          <tr><td>Effective BPM</td><td>${d.effective_bpm > 0 ? d.effective_bpm.toFixed(2) : "\u2014"}</td></tr>
          <tr><td>Pitch %</td><td>${d.original_bpm > 0 ? d.pitch_percent.toFixed(3) + "%" : "\u2014"}</td></tr>
          <tr><td>Position (ms)</td><td>${d.playback_position_ms > 0 ? d.playback_position_ms.toFixed(0) : "0"}</td></tr>
          <tr><td>Position (time)</td><td>${this._formatMs(d.playback_position_ms)}</td></tr>
          <tr><td>Track Length</td><td>${d.track_length_sec > 0 ? d.track_length_sec.toFixed(1) + "s" : "\u2014"}</td></tr>
          <tr><td>Beat #</td><td>${d.beat_number || "\u2014"}</td></tr>
          <tr><td>Beat in Bar</td><td>${d.beat_within_bar || "\u2014"} / 4</td></tr>
          <tr><td>Master</td><td>${d.is_master ? "YES" : "NO"}</td></tr>
          <tr><td>Sync</td><td>${d.is_synced ? "YES" : "NO"}</td></tr>
          <tr><td>Loop</td><td>${d.is_looping ? "YES" : "NO"}</td></tr>
          <tr><td>Track</td><td>${d.track_artist} \u2014 ${d.track_title}</td></tr>
          <tr><td>Key</td><td>${d.track_key || "\u2014"}</td></tr>
          <tr><td>Genre</td><td>${d.track_genre || "\u2014"}</td></tr>
          <tr><td>Rekordbox ID</td><td>${d.rekordbox_id || "\u2014"}</td></tr>
          <tr><td>Last Update</td><td>${d.last_update > 0 ? new Date(d.last_update * 1000).toLocaleTimeString() : "\u2014"}</td></tr>
        </table>
      </div>`;
    }

    if (!html) {
      html = '<div class="pioneer-data-empty">Waiting for beat-link-trigger OSC data on port 9000...</div>';
    }

    grid.innerHTML = html;
  }

  _setFlag(id, active) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("active", !!active);
  }

  _formatMs(ms) {
    if (!ms || ms <= 0) return "0:00.0";
    const totalSec = ms / 1000;
    const m = Math.floor(totalSec / 60);
    const s = Math.floor(totalSec % 60);
    const tenths = Math.floor((totalSec % 1) * 10);
    return `${m}:${s.toString().padStart(2, "0")}.${tenths}`;
  }

  _formatSec(sec) {
    if (!sec || sec <= 0) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }
}

// Auto-initialize
const pioneerLink = new PioneerLink();
