package com.scue.bridge;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Constructs typed JSON messages matching the SCUE bridge protocol and broadcasts
 * them via the WebSocket server.
 *
 * Per ADR-012: Only real-time playback messages are emitted.
 * Track metadata, beatgrids, waveforms, cue points, and phrase analysis are
 * handled by the Python side via rbox (for DLP hardware) or future bridge
 * extensions (for legacy hardware).
 *
 * All messages follow the envelope:
 * { "type": "...", "timestamp": ..., "player_number": ..., "payload": { ... } }
 */
public class MessageEmitter {

    private static final Logger log = LoggerFactory.getLogger(MessageEmitter.class);
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();

    private final BridgeWebSocketServer wsServer;

    public MessageEmitter(BridgeWebSocketServer wsServer) {
        this.wsServer = wsServer;
    }

    /**
     * Emit a message to all WebSocket clients.
     */
    public void emit(String type, Integer playerNumber, Map<String, Object> payload) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("type", type);
        envelope.put("timestamp", System.currentTimeMillis() / 1000.0);
        envelope.put("player_number", playerNumber);
        envelope.put("payload", payload);

        String json = GSON.toJson(envelope);
        log.debug("Emitting: {}", json);
        wsServer.broadcastMessage(json);
    }

    // ── Message types ───────────────────────────────────────────────────────

    public void emitBridgeStatus(boolean connected, int devicesOnline, String version, String error) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("connected", connected);
        payload.put("devices_online", devicesOnline);
        payload.put("version", version);
        if (error != null) {
            payload.put("error", error);
        }
        emit("bridge_status", null, payload);
    }

    public void emitDeviceFound(String deviceName, int deviceNumber, String deviceType,
                                 String ipAddress, Integer playerNumber, boolean usesDlp) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("device_name", deviceName);
        payload.put("device_number", deviceNumber);
        payload.put("device_type", deviceType);
        payload.put("ip_address", ipAddress);
        payload.put("uses_dlp", usesDlp);
        emit("device_found", playerNumber, payload);
    }

    public void emitDeviceLost(String deviceName, int deviceNumber, String deviceType,
                                String ipAddress, Integer playerNumber) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("device_name", deviceName);
        payload.put("device_number", deviceNumber);
        payload.put("device_type", deviceType);
        payload.put("ip_address", ipAddress);
        emit("device_lost", playerNumber, payload);
    }

    public void emitPlayerStatus(int playerNumber, double bpm, double pitch,
                                  int beatWithinBar, int beatNumber,
                                  String playbackState, boolean isOnAir,
                                  int trackSourcePlayer, String trackSourceSlot,
                                  String trackType, int rekordboxId) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("bpm", bpm);
        payload.put("pitch", pitch);
        payload.put("beat_within_bar", beatWithinBar);
        payload.put("beat_number", beatNumber);
        payload.put("playback_state", playbackState);
        payload.put("is_on_air", isOnAir);
        payload.put("track_source_player", trackSourcePlayer);
        payload.put("track_source_slot", trackSourceSlot);
        payload.put("track_type", trackType);
        payload.put("rekordbox_id", rekordboxId);
        emit("player_status", playerNumber, payload);
    }

    public void emitBeat(int playerNumber, int beatWithinBar, double bpm, double pitch) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("beat_within_bar", beatWithinBar);
        payload.put("bpm", bpm);
        payload.put("pitch", pitch);
        emit("beat", playerNumber, payload);
    }
}
