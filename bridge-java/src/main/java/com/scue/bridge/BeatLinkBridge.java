package com.scue.bridge;

import org.deepsymmetry.beatlink.*;
import org.deepsymmetry.beatlink.data.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.SocketException;
import java.util.*;
import java.util.concurrent.*;

/**
 * Beat-link bridge — connects to Pioneer DJ hardware via Pro DJ Link and streams
 * typed JSON messages over a local WebSocket to the SCUE Python process.
 *
 * Startup sequence follows the spec:
 *   1. Parse CLI args
 *   2. Start WebSocket server
 *   3. Emit bridge_status { connected: false }
 *   4-13. Initialize beat-link components in order
 *   14. Register listeners, emit bridge_status { connected: true }
 *
 * If hardware is not found, retries periodically.
 */
public class BeatLinkBridge {

    private static final Logger log = LoggerFactory.getLogger(BeatLinkBridge.class);
    private static final String VERSION = "1.0.0";

    private final int port;
    private final int playerNumber;
    private final int retryInterval;

    private BridgeWebSocketServer wsServer;
    private MessageEmitter emitter;
    private volatile boolean running = true;
    private volatile boolean beatLinkConnected = false;

    // Track which rekordbox IDs we've already sent metadata for (per player)
    private final Map<Integer, Integer> lastLoadedTrack = new ConcurrentHashMap<>();

    public BeatLinkBridge(int port, int playerNumber, int retryInterval) {
        this.port = port;
        this.playerNumber = playerNumber;
        this.retryInterval = retryInterval;
    }

    public void start() throws Exception {
        // Step 2: Start WebSocket server BEFORE beat-link
        wsServer = new BridgeWebSocketServer(port);
        wsServer.start();
        emitter = new MessageEmitter(wsServer);

        // Step 3: Emit initial bridge_status
        emitter.emitBridgeStatus(false, 0, VERSION, null);
        log.info("Bridge started on port {}", port);
        log.info("Claiming player number {}", playerNumber);

        // Register shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(this::shutdown));

        // Steps 4-13: Initialize beat-link (with retry), reconnect on drop
        while (running) {
            if (!beatLinkConnected) {
                try {
                    initBeatLink();
                } catch (Exception e) {
                    log.warn("Failed to initialize beat-link: {}. Retrying in {}s", e.getMessage(), retryInterval);
                    emitter.emitBridgeStatus(false, 0, VERSION, e.getMessage());
                    cleanupBeatLink();
                    try {
                        Thread.sleep(retryInterval * 1000L);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                    continue;
                }
            }

            // Monitor: if VirtualCdj dropped, trigger reconnect
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }

            if (beatLinkConnected && !VirtualCdj.getInstance().isRunning()) {
                log.warn("VirtualCdj stopped unexpectedly — reconnecting");
                beatLinkConnected = false;
                emitter.emitBridgeStatus(false, 0, VERSION, "VirtualCdj disconnected");
                cleanupBeatLink();
                try {
                    Thread.sleep(retryInterval * 1000L);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    private void initBeatLink() throws Exception {
        // Step 4: Start DeviceFinder
        DeviceFinder.getInstance().start();
        log.info("DeviceFinder started");

        // Step 5-6: Configure and start VirtualCdj
        VirtualCdj.getInstance().setDeviceNumber((byte) playerNumber);

        if (!VirtualCdj.getInstance().start()) {
            throw new RuntimeException("VirtualCdj failed to join the Pro DJ Link network (timeout)");
        }

        String iface = VirtualCdj.getInstance().getLocalAddress() != null
            ? VirtualCdj.getInstance().getLocalAddress().getHostAddress()
            : "unknown";
        log.info("Joined Pro DJ Link network on interface {} ({})", iface,
            VirtualCdj.getInstance().getLocalAddress());

        // Steps 7-11: Start finders
        MetadataFinder.getInstance().start();
        log.info("MetadataFinder started");

        BeatGridFinder.getInstance().start();
        log.info("BeatGridFinder started");

        WaveformFinder.getInstance().start();
        log.info("WaveformFinder started");

        CrateDigger.getInstance().start();
        log.info("CrateDigger started");

        try {
            AnalysisTagFinder.getInstance().start();
            log.info("AnalysisTagFinder started");
        } catch (Exception e) {
            log.warn("AnalysisTagFinder not available: {}", e.getMessage());
        }

        // Step 12: Register all listeners
        registerListeners();

        // Step 13: Emit connected status
        beatLinkConnected = true;
        int deviceCount = DeviceFinder.getInstance().getCurrentDevices().size();
        emitter.emitBridgeStatus(true, deviceCount, VERSION, null);
        log.info("Beat-link connected. {} devices online", deviceCount);

        // Emit device_found for any devices already present
        for (DeviceAnnouncement device : DeviceFinder.getInstance().getCurrentDevices()) {
            emitDeviceFound(device);
        }
    }

    private void registerListeners() throws SocketException {
        // Device announcement listener
        DeviceFinder.getInstance().addDeviceAnnouncementListener(new DeviceAnnouncementListener() {
            @Override
            public void deviceFound(DeviceAnnouncement device) {
                try {
                    emitDeviceFound(device);
                    int count = DeviceFinder.getInstance().getCurrentDevices().size();
                    emitter.emitBridgeStatus(true, count, VERSION, null);
                } catch (Exception e) {
                    log.error("Error in deviceFound listener: {}", e.getMessage(), e);
                }
            }

            @Override
            public void deviceLost(DeviceAnnouncement device) {
                try {
                    emitDeviceLost(device);
                    if (DeviceFinder.getInstance().isRunning()) {
                        int count = DeviceFinder.getInstance().getCurrentDevices().size();
                        emitter.emitBridgeStatus(true, count, VERSION, null);
                    }
                } catch (Exception e) {
                    log.error("Error in deviceLost listener: {}", e.getMessage(), e);
                }
            }
        });

        // CDJ status (player_status) listener — ~5Hz per player
        VirtualCdj.getInstance().addUpdateListener(update -> {
            try {
                if (update instanceof CdjStatus) {
                    handleCdjStatus((CdjStatus) update);
                }
            } catch (Exception e) {
                log.error("Error in update listener: {}", e.getMessage(), e);
            }
        });

        // Beat listener
        BeatFinder.getInstance().addBeatListener(beat -> {
            try {
                handleBeat(beat);
            } catch (Exception e) {
                log.error("Error in beat listener: {}", e.getMessage(), e);
            }
        });
        BeatFinder.getInstance().start();

        // Metadata listener — fires when track metadata becomes available
        MetadataFinder.getInstance().addTrackMetadataListener(new TrackMetadataListener() {
            @Override
            public void metadataChanged(TrackMetadataUpdate update) {
                try {
                    handleMetadataUpdate(update);
                } catch (Exception e) {
                    log.error("Error in metadata listener: {}", e.getMessage(), e);
                }
            }
        });

        // Beat grid listener
        BeatGridFinder.getInstance().addBeatGridListener(new BeatGridListener() {
            @Override
            public void beatGridChanged(BeatGridUpdate update) {
                try {
                    handleBeatGridUpdate(update);
                } catch (Exception e) {
                    log.error("Error in beatgrid listener: {}", e.getMessage(), e);
                }
            }
        });

        // Waveform listener
        WaveformFinder.getInstance().addWaveformListener(new WaveformListener() {
            @Override
            public void previewChanged(WaveformPreviewUpdate update) {
                // We only care about detail waveforms
            }

            @Override
            public void detailChanged(WaveformDetailUpdate update) {
                try {
                    handleWaveformDetail(update);
                } catch (Exception e) {
                    log.error("Error in waveform listener: {}", e.getMessage(), e);
                }
            }
        });

        log.info("All listeners registered");
    }

    // ── Event handlers ─────────────────────────────────────────────────────

    private void emitDeviceFound(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName();
        String ip = device.getAddress().getHostAddress();
        String type = classifyDevice(device);
        Integer playerNum = "cdj".equals(type) && num >= 1 && num <= 4 ? num : null;

        emitter.emitDeviceFound(name, num, type, ip, playerNum);
        log.info("Found device: {} (player {}) at {}", name, num, ip);
    }

    private void emitDeviceLost(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName();
        String ip = device.getAddress().getHostAddress();
        String type = classifyDevice(device);
        Integer playerNum = "cdj".equals(type) && num >= 1 && num <= 4 ? num : null;

        emitter.emitDeviceLost(name, num, type, ip, playerNum);
        log.info("Lost device: {} (player {})", name, num);
    }

    private void handleCdjStatus(CdjStatus status) {
        int pn = status.getDeviceNumber();
        // getEffectiveTempo() returns garbage when no track is loaded
        double bpm = status.getTrackType() == CdjStatus.TrackType.NO_TRACK
            ? 0.0 : status.getEffectiveTempo();
        // Pitch: beat-link raw is 0-2097152, center=1048576. Convert to percentage.
        double pitchPct = ((status.getPitch() / 1048576.0) - 1.0) * 100.0;
        int beatInBar = status.getBeatWithinBar();
        int beatNum = status.getBeatNumber();
        String playState = getPlaybackState(status);
        boolean onAir = status.isOnAir();
        int srcPlayer = status.getTrackSourcePlayer();
        String srcSlot = status.getTrackSourceSlot() != null
            ? status.getTrackSourceSlot().name().toLowerCase()
            : "unknown";
        String trackType = status.getTrackType() != null
            ? status.getTrackType().name().toLowerCase()
            : "unknown";

        emitter.emitPlayerStatus(pn, bpm, pitchPct, beatInBar, beatNum,
            playState, onAir, srcPlayer, srcSlot, trackType);
    }

    private void handleBeat(Beat beat) {
        int pn = beat.getDeviceNumber();
        int beatInBar = beat.getBeatWithinBar();
        double bpm = beat.getEffectiveTempo();
        double pitchPct = ((beat.getPitch() / 1048576.0) - 1.0) * 100.0;
        emitter.emitBeat(pn, beatInBar, bpm, pitchPct);
    }

    private void handleMetadataUpdate(TrackMetadataUpdate update) {
        int pn = update.player;
        TrackMetadata md = update.metadata;

        if (md == null) {
            // Track unloaded or metadata unavailable — emit with empty fields
            log.warn("No metadata available for player {}", pn);
            emitter.emitTrackMetadata(pn, "", "", "", "", "", 0, 0, null, 0, "", 0);
            return;
        }

        String title = md.getTitle() != null ? md.getTitle() : "";
        String artist = md.getArtist() != null ? md.getArtist().label : "";
        String album = md.getAlbum() != null ? md.getAlbum().label : "";
        String genre = md.getGenre() != null ? md.getGenre().label : "";
        String key = md.getKey() != null ? md.getKey().label : "";
        double bpm = md.getTempo() / 100.0;
        double duration = md.getDuration();
        String color = md.getColor() != null ? String.format("#%06X", md.getColor().color.getRGB() & 0xFFFFFF) : null;
        int rating = md.getRating();
        String comment = md.getComment() != null ? md.getComment() : "";

        // rekordbox ID: use the track's rekordbox ID from the CdjStatus
        CdjStatus latestStatus = (CdjStatus) VirtualCdj.getInstance().getLatestStatusFor(pn);
        int rbId = latestStatus != null ? latestStatus.getRekordboxId() : 0;

        emitter.emitTrackMetadata(pn, title, artist, album, genre, key, bpm, duration, color, rating, comment, rbId);
        log.info("Track loaded on player {}: {} — {}", pn, title, artist);
    }

    private void handleBeatGridUpdate(BeatGridUpdate update) {
        int pn = update.player;
        BeatGrid grid = update.beatGrid;

        if (grid == null) {
            return;
        }

        List<Map<String, Object>> beats = new ArrayList<>();
        for (int i = 1; i <= grid.beatCount; i++) {
            Map<String, Object> beat = new LinkedHashMap<>();
            beat.put("beat_number", i);
            beat.put("time_ms", (double) grid.getTimeWithinTrack(i));
            beat.put("bpm", grid.getBpm(i) / 100.0);
            beats.add(beat);
        }

        emitter.emitBeatGrid(pn, beats);
        log.info("Beat grid for player {}: {} beats", pn, grid.beatCount);
    }

    private void handleWaveformDetail(WaveformDetailUpdate update) {
        int pn = update.player;
        WaveformDetail detail = update.detail;

        if (detail == null) {
            return;
        }

        // Encode raw waveform bytes as base64
        String base64Data = Base64.getEncoder().encodeToString(detail.getData().array());
        // Estimate total beats from beat grid if available
        BeatGrid grid = BeatGridFinder.getInstance().getLatestBeatGridFor(pn);
        int totalBeats = grid != null ? grid.beatCount : 0;

        emitter.emitWaveformDetail(pn, base64Data, totalBeats);
        log.info("Waveform detail for player {}", pn);
    }

    /**
     * Clean up beat-link components so we can reinitialize cleanly.
     */
    private void cleanupBeatLink() {
        try { AnalysisTagFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { CrateDigger.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { WaveformFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { BeatGridFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { MetadataFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { BeatFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { if (VirtualCdj.getInstance().isRunning()) VirtualCdj.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { if (DeviceFinder.getInstance().isRunning()) DeviceFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    private String classifyDevice(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName().toLowerCase();
        // Device numbers 33+ are mixer channels on all-in-one units (XDJ-AZ, etc.)
        if (num >= 33 || name.contains("djm") || name.contains("mixer")) {
            return "djm";
        } else if (name.contains("rekordbox")) {
            return "rekordbox";
        }
        return "cdj";
    }

    private String getPlaybackState(CdjStatus status) {
        if (status.isPlaying()) return "playing";
        if (status.isPaused()) return "paused";
        if (status.isCued()) return "cued";
        if (status.isSearching()) return "searching";
        return "paused";
    }

    // ── Shutdown ────────────────────────────────────────────────────────────

    private void shutdown() {
        log.info("Shutting down beat-link bridge...");
        running = false;

        try {
            // Stop finders in reverse order
            try { AnalysisTagFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { CrateDigger.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { WaveformFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { BeatGridFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { MetadataFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { BeatFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }

            // Leave the Pro DJ Link network cleanly
            if (VirtualCdj.getInstance().isRunning()) {
                VirtualCdj.getInstance().stop();
                log.info("VirtualCdj stopped — left Pro DJ Link network");
            }

            if (DeviceFinder.getInstance().isRunning()) {
                DeviceFinder.getInstance().stop();
            }

            // Close WebSocket
            if (wsServer != null) {
                wsServer.stop(1000);
                log.info("WebSocket server stopped");
            }
        } catch (Exception e) {
            log.error("Error during shutdown: {}", e.getMessage(), e);
        }

        log.info("Bridge stopped");
    }

    // ── Main ────────────────────────────────────────────────────────────────

    public static void main(String[] args) {
        int port = 17400;
        int playerNumber = 5;
        int retryInterval = 10;
        String logLevel = "INFO";

        // Parse CLI arguments
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--port":
                    if (i + 1 < args.length) port = Integer.parseInt(args[++i]);
                    break;
                case "--player-number":
                    if (i + 1 < args.length) playerNumber = Integer.parseInt(args[++i]);
                    break;
                case "--retry-interval":
                    if (i + 1 < args.length) retryInterval = Integer.parseInt(args[++i]);
                    break;
                case "--log-level":
                    if (i + 1 < args.length) logLevel = args[++i];
                    break;
                default:
                    System.err.println("Unknown argument: " + args[i]);
                    System.err.println("Usage: java -jar beat-link-bridge.jar [--port N] [--player-number N] [--retry-interval S] [--log-level LEVEL]");
                    System.exit(1);
            }
        }

        // Configure SLF4J simple logger
        System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", logLevel.toLowerCase());
        System.setProperty("org.slf4j.simpleLogger.showDateTime", "true");
        System.setProperty("org.slf4j.simpleLogger.dateTimeFormat", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");
        System.setProperty("org.slf4j.simpleLogger.logFile", "System.err");

        BeatLinkBridge bridge = new BeatLinkBridge(port, playerNumber, retryInterval);
        try {
            bridge.start();
        } catch (Exception e) {
            log.error("Fatal error: {}", e.getMessage(), e);
            System.exit(1);
        }
    }
}
