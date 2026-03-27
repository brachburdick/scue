package com.scue.bridge;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import org.deepsymmetry.beatlink.*;
import org.deepsymmetry.beatlink.data.*;
import org.deepsymmetry.beatlink.dbserver.ConnectionManager;
import org.deepsymmetry.beatlink.dbserver.Message;
import org.deepsymmetry.beatlink.dbserver.NumberField;
import org.deepsymmetry.beatlink.dbserver.StringField;
import org.deepsymmetry.beatlink.dbserver.Field;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Routes incoming WebSocket commands to beat-link APIs and sends responses.
 *
 * Commands are JSON objects with { "command", "request_id", "params" }.
 * Responses go back as { "type": "command_response", "timestamp", "player_number", "payload" }.
 *
 * Supported commands:
 *   - browse_root_menu: list top-level folders/playlists on a USB/SD slot
 *   - browse_playlist: list tracks in a folder/playlist
 *   - browse_all_tracks: flat list of all tracks on a slot
 *   - load_track: load a specific track onto a deck
 */
public class CommandHandler {

    private static final Logger log = LoggerFactory.getLogger(CommandHandler.class);
    private static final Gson GSON = new GsonBuilder().serializeNulls().create();

    private final MessageEmitter emitter;

    // Commands run on a separate thread to avoid blocking the WebSocket read loop
    private final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "command-handler");
        t.setDaemon(true);
        return t;
    });

    public CommandHandler(MessageEmitter emitter) {
        this.emitter = emitter;
    }

    /**
     * Parse and dispatch a command received from a WebSocket client.
     * Called from BridgeWebSocketServer.onMessage().
     */
    public void handleCommand(String rawJson) {
        executor.submit(() -> {
            try {
                @SuppressWarnings("unchecked")
                Map<String, Object> msg = GSON.fromJson(rawJson, Map.class);

                String command = (String) msg.get("command");
                String requestId = (String) msg.get("request_id");
                @SuppressWarnings("unchecked")
                Map<String, Object> params = (Map<String, Object>) msg.getOrDefault("params", Map.of());

                if (command == null || requestId == null) {
                    log.warn("Received command without 'command' or 'request_id': {}", rawJson);
                    return;
                }

                log.info("Command received: {} (request_id={})", command, requestId);

                switch (command) {
                    case "browse_root_menu":
                        handleBrowseRootMenu(requestId, params);
                        break;
                    case "browse_playlist":
                        handleBrowsePlaylist(requestId, params);
                        break;
                    case "browse_all_tracks":
                        handleBrowseAllTracks(requestId, params);
                        break;
                    case "load_track":
                        handleLoadTrack(requestId, params);
                        break;
                    default:
                        emitError(requestId, command, "Unknown command: " + command);
                }
            } catch (Exception e) {
                log.error("Error handling command: {}", e.getMessage(), e);
            }
        });
    }

    // ── Command handlers ─────────────────────────────────────────────────────

    private void handleBrowseRootMenu(String requestId, Map<String, Object> params) {
        try {
            int playerNumber = toInt(params.get("player_number"));
            CdjStatus.TrackSourceSlot slot = parseSlot((String) params.get("slot"));
            SlotReference slotRef = SlotReference.getSlotReference(playerNumber, slot);

            if (!ConnectionManager.getInstance().isRunning()) {
                emitError(requestId, "browse_root_menu", "ConnectionManager not running — metadata queries unavailable");
                return;
            }

            List<Message> items = MenuLoader.getInstance().requestRootMenuFrom(slotRef, 0);
            if (items == null) {
                emitError(requestId, "browse_root_menu", "No response from player " + playerNumber);
                return;
            }

            List<Map<String, Object>> menuItems = new ArrayList<>();
            for (Message item : items) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("item_type", safeMenuItemType(item));
                entry.put("text1", getStringArg(item, 3));
                entry.put("text2", getStringArg(item, 5));
                entry.put("id", getNumberArg(item, 1));
                menuItems.add(entry);
            }

            emitOk(requestId, "browse_root_menu", Map.of(
                "player_number", playerNumber,
                "slot", params.get("slot"),
                "items", menuItems
            ));
            log.info("browse_root_menu: {} items from player {}", menuItems.size(), playerNumber);

        } catch (Exception e) {
            log.error("browse_root_menu failed: {}", e.getMessage(), e);
            emitError(requestId, "browse_root_menu", e.getMessage());
        }
    }

    private void handleBrowsePlaylist(String requestId, Map<String, Object> params) {
        try {
            int playerNumber = toInt(params.get("player_number"));
            int folderId = toInt(params.get("folder_id"));
            boolean isFolder = params.containsKey("is_folder") ? toBool(params.get("is_folder")) : true;
            CdjStatus.TrackSourceSlot slot = parseSlot((String) params.get("slot"));

            if (!ConnectionManager.getInstance().isRunning()) {
                emitError(requestId, "browse_playlist", "ConnectionManager not running");
                return;
            }

            // Use MetadataFinder.requestPlaylistItemsFrom — supports folder hierarchy
            // navigation. isFolder=true lists sub-folders/playlists, isFolder=false
            // lists tracks within a leaf playlist.
            List<Message> items = MetadataFinder.getInstance().requestPlaylistItemsFrom(
                playerNumber, slot, 0, folderId, isFolder);
            if (items == null) {
                emitError(requestId, "browse_playlist", "No response from player " + playerNumber);
                return;
            }

            List<Map<String, Object>> tracks = new ArrayList<>();
            for (Message item : items) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("item_type", safeMenuItemType(item));
                entry.put("title", getStringArg(item, 3));
                entry.put("artist", getStringArg(item, 5));
                entry.put("rekordbox_id", getNumberArg(item, 1));
                tracks.add(entry);
            }

            emitOk(requestId, "browse_playlist", Map.of(
                "player_number", playerNumber,
                "slot", params.get("slot"),
                "folder_id", folderId,
                "is_folder", isFolder,
                "items", tracks
            ));
            log.info("browse_playlist: {} items from player {} folder {} (isFolder={})",
                tracks.size(), playerNumber, folderId, isFolder);

        } catch (Exception e) {
            log.error("browse_playlist failed: {}", e.getMessage(), e);
            emitError(requestId, "browse_playlist", e.getMessage());
        }
    }

    private void handleBrowseAllTracks(String requestId, Map<String, Object> params) {
        try {
            int playerNumber = toInt(params.get("player_number"));
            CdjStatus.TrackSourceSlot slot = parseSlot((String) params.get("slot"));
            SlotReference slotRef = SlotReference.getSlotReference(playerNumber, slot);

            if (!ConnectionManager.getInstance().isRunning()) {
                emitError(requestId, "browse_all_tracks", "ConnectionManager not running");
                return;
            }

            // Request the full track list via the track menu — may be large
            List<Message> items = MenuLoader.getInstance().requestTrackMenuFrom(slotRef, 0);
            if (items == null) {
                emitError(requestId, "browse_all_tracks", "No response from player " + playerNumber);
                return;
            }

            List<Map<String, Object>> tracks = new ArrayList<>();
            for (Message item : items) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("title", getStringArg(item, 3));
                entry.put("artist", getStringArg(item, 5));
                entry.put("rekordbox_id", getNumberArg(item, 1));
                tracks.add(entry);
            }

            emitOk(requestId, "browse_all_tracks", Map.of(
                "player_number", playerNumber,
                "slot", params.get("slot"),
                "track_count", tracks.size(),
                "tracks", tracks
            ));
            log.info("browse_all_tracks: {} tracks from player {}", tracks.size(), playerNumber);

        } catch (Exception e) {
            log.error("browse_all_tracks failed: {}", e.getMessage(), e);
            emitError(requestId, "browse_all_tracks", e.getMessage());
        }
    }

    private void handleLoadTrack(String requestId, Map<String, Object> params) {
        try {
            int targetPlayer = toInt(params.get("target_player"));
            int rekordboxId = toInt(params.get("rekordbox_id"));
            int sourcePlayer = toInt(params.get("source_player"));
            String sourceSlotName = (String) params.get("source_slot");
            String sourceTypeName = (String) params.getOrDefault("source_type", "rekordbox");

            CdjStatus.TrackSourceSlot sourceSlot = parseSlot(sourceSlotName);
            CdjStatus.TrackType sourceType = parseTrackType(sourceTypeName);

            log.info("Loading track: rbid={} onto player {} from player {} slot {}",
                rekordboxId, targetPlayer, sourcePlayer, sourceSlotName);

            VirtualCdj.getInstance().sendLoadTrackCommand(
                targetPlayer,
                rekordboxId,
                sourcePlayer,
                sourceSlot,
                sourceType
            );

            emitOk(requestId, "load_track", Map.of(
                "target_player", targetPlayer,
                "rekordbox_id", rekordboxId,
                "source_player", sourcePlayer,
                "source_slot", sourceSlotName
            ));
            log.info("load_track command sent: rbid={} -> player {}", rekordboxId, targetPlayer);

        } catch (Exception e) {
            log.error("load_track failed: {}", e.getMessage(), e);
            emitError(requestId, "load_track", e.getMessage());
        }
    }

    // ── Response helpers ─────────────────────────────────────────────────────

    private void emitOk(String requestId, String command, Map<String, Object> data) {
        emitter.emitCommandResponse(requestId, "ok", command, data, null);
    }

    private void emitError(String requestId, String command, String errorMessage) {
        emitter.emitCommandResponse(requestId, "error", command, Map.of(), errorMessage);
    }

    // ── Message field extraction helpers ─────────────────────────────────────

    /**
     * Extract a string argument from a dbserver Message by index.
     * Menu result messages typically have: [1]=ID, [3]=text1, [5]=text2.
     */
    private String getStringArg(Message msg, int index) {
        List<Field> args = msg.arguments;
        if (args != null && index < args.size() && args.get(index) instanceof StringField) {
            return ((StringField) args.get(index)).getValue();
        }
        return "";
    }

    /**
     * Extract a numeric argument from a dbserver Message by index.
     */
    private int getNumberArg(Message msg, int index) {
        List<Field> args = msg.arguments;
        if (args != null && index < args.size() && args.get(index) instanceof NumberField) {
            return (int) ((NumberField) args.get(index)).getValue();
        }
        return 0;
    }

    /**
     * Safely get the menu item type name, or "unknown" if not available.
     */
    private String safeMenuItemType(Message msg) {
        try {
            Message.MenuItemType type = msg.getMenuItemType();
            return type != null ? type.name().toLowerCase() : "unknown";
        } catch (Exception e) {
            return "unknown";
        }
    }

    // ── Parse helpers ────────────────────────────────────────────────────────

    private CdjStatus.TrackSourceSlot parseSlot(String slotName) {
        if (slotName == null) return CdjStatus.TrackSourceSlot.USB_SLOT;
        switch (slotName.toLowerCase()) {
            case "sd":
                return CdjStatus.TrackSourceSlot.SD_SLOT;
            case "usb":
                return CdjStatus.TrackSourceSlot.USB_SLOT;
            case "collection":
                return CdjStatus.TrackSourceSlot.COLLECTION;
            default:
                return CdjStatus.TrackSourceSlot.USB_SLOT;
        }
    }

    private CdjStatus.TrackType parseTrackType(String typeName) {
        if (typeName == null) return CdjStatus.TrackType.REKORDBOX;
        switch (typeName.toLowerCase()) {
            case "rekordbox":
                return CdjStatus.TrackType.REKORDBOX;
            case "unanalyzed":
                return CdjStatus.TrackType.UNANALYZED;
            case "cd":
                return CdjStatus.TrackType.CD_DIGITAL_AUDIO;
            default:
                return CdjStatus.TrackType.REKORDBOX;
        }
    }

    private int toInt(Object value) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        if (value instanceof String) {
            return Integer.parseInt((String) value);
        }
        throw new IllegalArgumentException("Cannot convert to int: " + value);
    }

    private boolean toBool(Object value) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value instanceof String) {
            return Boolean.parseBoolean((String) value);
        }
        return false;
    }

    /**
     * Clean up the executor on shutdown.
     */
    public void shutdown() {
        executor.shutdownNow();
    }
}
