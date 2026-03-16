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

    // ── Convenience methods for each message type ──────────────────────────

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

    public void emitDeviceFound(String deviceName, int deviceNumber, String deviceType, String ipAddress, Integer playerNumber) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("device_name", deviceName);
        payload.put("device_number", deviceNumber);
        payload.put("device_type", deviceType);
        payload.put("ip_address", ipAddress);
        emit("device_found", playerNumber, payload);
    }

    public void emitDeviceLost(String deviceName, int deviceNumber, String deviceType, String ipAddress, Integer playerNumber) {
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
                                  String trackType) {
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
        emit("player_status", playerNumber, payload);
    }

    public void emitTrackMetadata(int playerNumber, String title, String artist,
                                   String album, String genre, String key,
                                   double bpm, double duration, String color,
                                   int rating, String comment, int rekordboxId) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("title", title);
        payload.put("artist", artist);
        payload.put("album", album);
        payload.put("genre", genre);
        payload.put("key", key);
        payload.put("bpm", bpm);
        payload.put("duration", duration);
        payload.put("color", color);
        payload.put("rating", rating);
        payload.put("comment", comment);
        payload.put("rekordbox_id", rekordboxId);
        emit("track_metadata", playerNumber, payload);
    }

    public void emitBeatGrid(int playerNumber, java.util.List<Map<String, Object>> beats) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("beats", beats);
        emit("beat_grid", playerNumber, payload);
    }

    public void emitWaveformDetail(int playerNumber, String base64Data, int totalBeats) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("data", base64Data);
        payload.put("total_beats", totalBeats);
        emit("waveform_detail", playerNumber, payload);
    }

    public void emitPhraseAnalysis(int playerNumber, java.util.List<Map<String, Object>> phrases) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("phrases", phrases);
        emit("phrase_analysis", playerNumber, payload);
    }

    public void emitCuePoints(int playerNumber,
                               java.util.List<Map<String, Object>> cuePoints,
                               java.util.List<Map<String, Object>> memoryPoints,
                               java.util.List<Map<String, Object>> hotCues) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("cue_points", cuePoints);
        payload.put("memory_points", memoryPoints);
        payload.put("hot_cues", hotCues);
        emit("cue_points", playerNumber, payload);
    }

    public void emitBeat(int playerNumber, int beatWithinBar, double bpm, double pitch) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("beat_within_bar", beatWithinBar);
        payload.put("bpm", bpm);
        payload.put("pitch", pitch);
        emit("beat", playerNumber, payload);
    }
}
