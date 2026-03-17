package com.scue.bridge;

import org.deepsymmetry.beatlink.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.SocketException;
import java.util.*;
import java.util.concurrent.*;

/**
 * Beat-link bridge — connects to Pioneer DJ hardware via Pro DJ Link and streams
 * typed JSON messages over a local WebSocket to the SCUE Python process.
 *
 * Per ADR-012: This bridge provides REAL-TIME PLAYBACK DATA ONLY:
 *   - player_status (BPM, pitch, beat position, play state, on-air, rekordbox ID)
 *   - beat events
 *   - device discovery
 *
 * Track metadata, beatgrids, waveforms, cue points, and phrase analysis are NOT
 * provided by the bridge. For Device Library Plus hardware (XDJ-AZ, Opus Quad, etc.),
 * the Python side reads metadata directly from the USB via the rbox library.
 * For legacy hardware, a separate metadata path may be added in future.
 *
 * Startup sequence:
 *   1. Parse CLI args
 *   2. Start WebSocket server
 *   3. Emit bridge_status { connected: false }
 *   4. Start DeviceFinder
 *   5. Configure and start VirtualCdj
 *   6. Start BeatFinder
 *   7. Register listeners, emit bridge_status { connected: true }
 */
public class BeatLinkBridge {

    private static final Logger log = LoggerFactory.getLogger(BeatLinkBridge.class);
    private static final String VERSION = "1.1.0";

    // Known Device Library Plus hardware models
    private static final Set<String> DLP_DEVICES = Set.of(
        "xdj-az", "opus-quad", "omnis-duo", "cdj-3000x"
    );

    private final int port;
    private final int playerNumber;
    private final int retryInterval;

    private BridgeWebSocketServer wsServer;
    private MessageEmitter emitter;
    private volatile boolean running = true;
    private volatile boolean beatLinkConnected = false;

    // Track the last known rekordbox ID per player for track-change detection
    private final Map<Integer, Integer> lastRekordboxId = new ConcurrentHashMap<>();
    // Track which devices use DLP (detected from device name)
    private final Set<String> dlpDeviceIps = ConcurrentHashMap.newKeySet();

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

        // Initialize beat-link (with retry), reconnect on drop
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
        // Start DeviceFinder
        DeviceFinder.getInstance().start();
        log.info("DeviceFinder started");

        // Configure and start VirtualCdj
        VirtualCdj.getInstance().setDeviceNumber((byte) playerNumber);

        if (!VirtualCdj.getInstance().start()) {
            throw new RuntimeException("VirtualCdj failed to join the Pro DJ Link network (timeout)");
        }

        String iface = VirtualCdj.getInstance().getLocalAddress() != null
            ? VirtualCdj.getInstance().getLocalAddress().getHostAddress()
            : "unknown";
        log.info("Joined Pro DJ Link network on interface {}", iface);

        // Register all listeners
        registerListeners();

        // Emit connected status
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
                    dlpDeviceIps.remove(device.getAddress().getHostAddress());
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

        log.info("All listeners registered (real-time data only, no metadata finders)");
    }

    // ── Event handlers ─────────────────────────────────────────────────────

    private void emitDeviceFound(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName();
        String ip = device.getAddress().getHostAddress();
        String type = classifyDevice(device);
        boolean usesDlp = isDlpDevice(name);

        if (usesDlp) {
            dlpDeviceIps.add(ip);
            log.info("Device {} uses Device Library Plus — metadata will come from rbox, not bridge", name);
        }

        Integer playerNum = "cdj".equals(type) && num >= 1 && num <= 4 ? num : null;
        emitter.emitDeviceFound(name, num, type, ip, playerNum, usesDlp);
        log.info("Found device: {} (number {}, type {}, dlp={}) at {}", name, num, type, usesDlp, ip);
    }

    private void emitDeviceLost(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName();
        String ip = device.getAddress().getHostAddress();
        String type = classifyDevice(device);
        Integer playerNum = "cdj".equals(type) && num >= 1 && num <= 4 ? num : null;

        emitter.emitDeviceLost(name, num, type, ip, playerNum);
        log.info("Lost device: {} (number {})", name, num);
    }

    private void handleCdjStatus(CdjStatus status) {
        int pn = status.getDeviceNumber();
        double bpm = status.getTrackType() == CdjStatus.TrackType.NO_TRACK
            ? 0.0 : status.getEffectiveTempo();
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
        int rekordboxId = status.getRekordboxId();

        emitter.emitPlayerStatus(pn, bpm, pitchPct, beatInBar, beatNum,
            playState, onAir, srcPlayer, srcSlot, trackType, rekordboxId);

        // Track-change detection: log when rekordbox ID changes.
        // The Python side uses this ID to look up metadata in the rbox database.
        Integer prevId = lastRekordboxId.put(pn, rekordboxId);
        if (prevId != null && prevId != rekordboxId) {
            if (rekordboxId == 0) {
                log.info("Track unloaded on player {}", pn);
            } else {
                log.info("Track change on player {}: rbid {} → {} (type={})", pn, prevId, rekordboxId, trackType);
            }
        } else if (prevId == null && rekordboxId != 0) {
            log.info("First track detected on player {}: rbid {} (type={})", pn, rekordboxId, trackType);
        }
    }

    private void handleBeat(Beat beat) {
        int pn = beat.getDeviceNumber();
        int beatInBar = beat.getBeatWithinBar();
        double bpm = beat.getEffectiveTempo();
        double pitchPct = ((beat.getPitch() / 1048576.0) - 1.0) * 100.0;
        emitter.emitBeat(pn, beatInBar, bpm, pitchPct);
    }

    /**
     * Clean up beat-link components so we can reinitialize cleanly.
     */
    private void cleanupBeatLink() {
        try { BeatFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { if (VirtualCdj.getInstance().isRunning()) VirtualCdj.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { if (DeviceFinder.getInstance().isRunning()) DeviceFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    private String classifyDevice(DeviceAnnouncement device) {
        int num = device.getDeviceNumber();
        String name = device.getDeviceName().toLowerCase();
        if (num >= 33 || name.contains("djm") || name.contains("mixer")) {
            return "djm";
        } else if (name.contains("rekordbox")) {
            return "rekordbox";
        }
        return "cdj";
    }

    private boolean isDlpDevice(String deviceName) {
        String lower = deviceName.toLowerCase().replaceAll("[\\s_]", "-");
        for (String dlp : DLP_DEVICES) {
            if (lower.contains(dlp)) {
                return true;
            }
        }
        return false;
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
            try { BeatFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }

            if (VirtualCdj.getInstance().isRunning()) {
                VirtualCdj.getInstance().stop();
                log.info("VirtualCdj stopped — left Pro DJ Link network");
            }

            if (DeviceFinder.getInstance().isRunning()) {
                DeviceFinder.getInstance().stop();
            }

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
