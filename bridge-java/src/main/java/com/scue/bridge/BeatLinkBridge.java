package com.scue.bridge;

import org.deepsymmetry.beatlink.*;
import org.deepsymmetry.beatlink.data.*;
import org.deepsymmetry.cratedigger.pdb.RekordboxAnlz;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.net.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Collectors;

/**
 * Beat-link bridge — connects to Pioneer DJ hardware via Pro DJ Link and streams
 * typed JSON messages over a local WebSocket to the SCUE Python process.
 *
 * Per ADR-017 (supersedes ADR-012): This bridge provides real-time playback data
 * AND metadata/analysis data via beat-link Finders:
 *   - player_status, beat events, device discovery (real-time)
 *   - track_metadata, beat_grid, waveform_detail, phrase_analysis, cue_points (via Finders)
 *
 * beat-link 8.1.0-SNAPSHOT has native XDJ-AZ support via CrateDigger NFS downloads
 * and SQLite ID translation. All Finders are enabled.
 *
 * Startup sequence:
 *   1. Parse CLI args (--port, --player-number, --interface, --database-key)
 *   2. Start WebSocket server
 *   3. Emit bridge_status { connected: false }
 *   4. Select network interface (auto-detect with scoring, or user-specified)
 *   5. Start DeviceFinder
 *   6. Configure and start VirtualCdj on selected interface
 *   7. Start BeatFinder
 *   8. Start all Finders (TimeFinder, MetadataFinder, BeatGridFinder, WaveformFinder, AnalysisTagFinder, ArtFinder)
 *   9. Register listeners, emit bridge_status { connected: true, network_interface: ..., interface_candidates: [...] }
 */
public class BeatLinkBridge {

    private static final Logger log = LoggerFactory.getLogger(BeatLinkBridge.class);
    private static final String VERSION = "2.0.0";

    // Known Device Library Plus hardware models
    private static final Set<String> DLP_DEVICES = Set.of(
        "xdj-az", "opus-quad", "omnis-duo", "cdj-3000x"
    );

    // Virtual interface name prefixes to filter out during auto-detection
    private static final Set<String> VIRTUAL_PREFIXES = Set.of(
        "veth", "docker", "br-", "vmnet", "utun", "awdl", "llw", "bridge"
    );

    private final int port;
    private final int playerNumber;
    private final int retryInterval;
    private final String requestedInterface; // null = auto-detect
    private final String databaseKey; // DLP database key for exportLibrary.db decryption

    private BridgeWebSocketServer wsServer;
    private MessageEmitter emitter;
    private volatile boolean running = true;
    private volatile boolean beatLinkConnected = false;

    // Network interface selection results (persisted for bridge_status messages)
    private NetworkInterface selectedInterface;
    private String selectedInterfaceName;
    private String selectedInterfaceAddress;
    private List<Map<String, Object>> interfaceCandidates;
    private String interfaceWarning;

    // Track the last known rekordbox ID per player for track-change detection
    private final Map<Integer, Integer> lastRekordboxId = new ConcurrentHashMap<>();
    // Track which devices use DLP (detected from device name)
    private final Set<String> dlpDeviceIps = ConcurrentHashMap.newKeySet();

    public BeatLinkBridge(int port, int playerNumber, int retryInterval, String requestedInterface, String databaseKey) {
        this.port = port;
        this.playerNumber = playerNumber;
        this.retryInterval = retryInterval;
        this.requestedInterface = requestedInterface;
        this.databaseKey = databaseKey;
    }

    public void start() throws Exception {
        // Step 2: Start WebSocket server BEFORE beat-link
        wsServer = new BridgeWebSocketServer(port);
        wsServer.start();
        emitter = new MessageEmitter(wsServer);

        // Step 3: Emit initial bridge_status
        emitter.emitBridgeStatus(false, 0, VERSION, null, null, null, null, null);
        log.info("Bridge started on port {}", port);
        log.info("Claiming player number {}", playerNumber);

        // Step 4: Select network interface
        selectNetworkInterface();

        // Register shutdown hook
        Runtime.getRuntime().addShutdownHook(new Thread(this::shutdown));

        // Initialize beat-link (with retry), reconnect on drop
        while (running) {
            if (!beatLinkConnected) {
                try {
                    initBeatLink();
                } catch (Exception e) {
                    log.warn("Failed to initialize beat-link: {}. Retrying in {}s", e.getMessage(), retryInterval);
                    emitter.emitBridgeStatus(false, 0, VERSION, e.getMessage(),
                        selectedInterfaceName, selectedInterfaceAddress, interfaceCandidates, interfaceWarning);
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
                emitter.emitBridgeStatus(false, 0, VERSION, "VirtualCdj disconnected",
                    selectedInterfaceName, selectedInterfaceAddress, interfaceCandidates, interfaceWarning);
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

    // ── Network interface selection ─────────────────────────────────────────

    /**
     * Select the network interface to bind to. Implements the three-layer strategy:
     *   Layer 1: Smart auto-detection with scoring (default)
     *   Layer 2: User-specified via --interface CLI arg
     *   Layer 3: Startup validation
     */
    private void selectNetworkInterface() throws SocketException {
        interfaceWarning = null;

        // Build candidate list with scores (always, for bridge_status reporting)
        interfaceCandidates = scoreAllInterfaces();

        if (requestedInterface != null) {
            // Layer 2: User-specified
            NetworkInterface userIface = NetworkInterface.getByName(requestedInterface);
            if (userIface != null && userIface.isUp()) {
                selectedInterface = userIface;
                selectedInterfaceName = userIface.getName();
                selectedInterfaceAddress = getInterfaceAddress(userIface);
                log.info("Using configured interface {} ({})", selectedInterfaceName, selectedInterfaceAddress);
                return;
            }

            // Fallback with warning
            if (userIface == null) {
                interfaceWarning = String.format("Configured interface %s not found. Falling back to auto-detection.", requestedInterface);
            } else {
                interfaceWarning = String.format("Configured interface %s exists but is down. Falling back to auto-detection.", requestedInterface);
            }
            log.warn(interfaceWarning);
        }

        // Layer 1: Auto-detection with scoring
        if (interfaceCandidates.isEmpty()) {
            log.warn("No suitable network interfaces found for auto-detection");
            selectedInterface = null;
            selectedInterfaceName = null;
            selectedInterfaceAddress = null;
            return;
        }

        // Pick the highest-scoring candidate
        Map<String, Object> best = interfaceCandidates.get(0); // already sorted by score desc
        String bestName = (String) best.get("name");
        selectedInterface = NetworkInterface.getByName(bestName);
        selectedInterfaceName = bestName;
        selectedInterfaceAddress = (String) best.get("address");

        // Log the decision
        StringBuilder otherCandidates = new StringBuilder();
        for (int i = 1; i < interfaceCandidates.size(); i++) {
            Map<String, Object> c = interfaceCandidates.get(i);
            if (otherCandidates.length() > 0) otherCandidates.append(", ");
            otherCandidates.append(String.format("%s (%s, score=%d, %s)",
                c.get("name"), c.get("address"), ((Number) c.get("score")).intValue(), c.get("type")));
        }
        log.info("Auto-selected interface {} ({}, score={}). Other candidates: {}",
            selectedInterfaceName, selectedInterfaceAddress, best.get("score"),
            otherCandidates.length() > 0 ? otherCandidates.toString() : "none");
    }

    /**
     * Score all network interfaces for Pro DJ Link suitability.
     * Returns list sorted by score descending.
     */
    private List<Map<String, Object>> scoreAllInterfaces() throws SocketException {
        List<Map<String, Object>> candidates = new ArrayList<>();

        Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
        if (interfaces == null) return candidates;

        while (interfaces.hasMoreElements()) {
            NetworkInterface iface = interfaces.nextElement();

            // Filter out loopback and down interfaces
            if (iface.isLoopback() || !iface.isUp()) continue;

            // Filter out virtual interfaces
            String name = iface.getName().toLowerCase();
            boolean isVirtual = VIRTUAL_PREFIXES.stream().anyMatch(name::startsWith);
            if (isVirtual) continue;

            // Get the first non-loopback IPv4 address
            String address = null;
            boolean hasLinkLocal = false;
            boolean hasPrivate = false;
            for (Enumeration<InetAddress> addrs = iface.getInetAddresses(); addrs.hasMoreElements(); ) {
                InetAddress addr = addrs.nextElement();
                if (addr instanceof Inet4Address && !addr.isLoopbackAddress()) {
                    if (address == null) address = addr.getHostAddress();
                    if (addr.isLinkLocalAddress()) hasLinkLocal = true;
                    String ip = addr.getHostAddress();
                    if (ip.startsWith("10.") || ip.startsWith("192.168.")) hasPrivate = true;
                }
            }

            if (address == null) continue; // No usable IPv4 address

            // Score the interface
            int score = 0;
            String type = "unknown";

            // +10 for link-local (169.254.x.x) — Pro DJ Link auto-config range
            if (hasLinkLocal) score += 10;

            // Classify interface type
            if (isWiredEthernet(iface)) {
                type = "ethernet";
                score += 5;
            } else if (isWifi(iface)) {
                type = "wifi";
                score -= 5;
            } else if (name.startsWith("utun") || name.startsWith("tun") || name.startsWith("tap")) {
                type = "vpn";
                score -= 10;
            } else {
                type = "other";
            }

            // +3 for private ranges (common manual DJ network configs)
            if (hasPrivate) score += 3;

            Map<String, Object> candidate = new LinkedHashMap<>();
            candidate.put("name", iface.getName());
            candidate.put("address", address);
            candidate.put("type", type);
            candidate.put("score", score);
            candidate.put("selected", false); // will be set to true for the chosen one
            candidates.add(candidate);
        }

        // Sort by score descending
        candidates.sort((a, b) -> ((Integer) b.get("score")).compareTo((Integer) a.get("score")));

        // Mark the top candidate as selected
        if (!candidates.isEmpty()) {
            candidates.get(0).put("selected", true);
        }

        return candidates;
    }

    /**
     * Heuristic: is this a wired Ethernet interface?
     * On macOS: en0-en9 that are NOT Wi-Fi. On Linux: eth*. On Windows: Ethernet*.
     */
    private boolean isWiredEthernet(NetworkInterface iface) {
        String name = iface.getName().toLowerCase();
        // Linux
        if (name.startsWith("eth")) return true;
        // macOS: en0-en99 that are not Wi-Fi
        if (name.matches("en\\d+") && !isWifi(iface)) return true;
        // Windows
        if (name.toLowerCase().startsWith("ethernet")) return true;
        return false;
    }

    /**
     * Heuristic: is this a Wi-Fi interface?
     * Checks display name (which java.net provides on some platforms) and common naming patterns.
     */
    private boolean isWifi(NetworkInterface iface) {
        String name = iface.getName().toLowerCase();
        String displayName = iface.getDisplayName() != null ? iface.getDisplayName().toLowerCase() : "";

        // Common Wi-Fi indicators
        if (name.startsWith("wlan") || name.equals("wi-fi")) return true;
        if (displayName.contains("wi-fi") || displayName.contains("wifi") ||
            displayName.contains("wireless") || displayName.contains("airport")) return true;

        // macOS: en0 is typically Wi-Fi (but not always). Check if it supports multicast
        // and has a display name suggesting wireless. This is imperfect but reasonable.
        if (name.equals("en0") && (displayName.contains("wi-fi") || displayName.contains("wireless"))) {
            return true;
        }

        return false;
    }

    /**
     * Get the first non-loopback IPv4 address of an interface, or "unknown".
     */
    private String getInterfaceAddress(NetworkInterface iface) {
        for (Enumeration<InetAddress> addrs = iface.getInetAddresses(); addrs.hasMoreElements(); ) {
            InetAddress addr = addrs.nextElement();
            if (addr instanceof Inet4Address && !addr.isLoopbackAddress()) {
                return addr.getHostAddress();
            }
        }
        return "unknown";
    }

    /**
     * On macOS, check if the 169.254.255.255 broadcast route points to the selected interface.
     * If not, VirtualCdj.start() will probe the wrong interface and time out.
     * Emits a warning but does not fail — the user may have already fixed the route.
     */
    private void checkBroadcastRoute() {
        try {
            ProcessBuilder pb = new ProcessBuilder("route", "get", "169.254.255.255");
            pb.redirectErrorStream(true);
            Process proc = pb.start();
            String output = new String(proc.getInputStream().readAllBytes());
            proc.waitFor();

            // Look for "interface: en16" in the output
            boolean routeOk = false;
            for (String line : output.split("\n")) {
                String trimmed = line.trim();
                if (trimmed.startsWith("interface:")) {
                    String routeIface = trimmed.substring("interface:".length()).trim();
                    if (routeIface.equals(selectedInterfaceName)) {
                        routeOk = true;
                        log.info("macOS broadcast route 169.254.255.255 → {} (correct)", routeIface);
                    } else {
                        interfaceWarning = String.format(
                            "macOS routes 169.254.255.255 via %s, not %s. "
                            + "Run: sudo route delete 169.254.255.255 && sudo route add -host 169.254.255.255 -interface %s",
                            routeIface, selectedInterfaceName, selectedInterfaceName);
                        log.warn(interfaceWarning);
                    }
                    break;
                }
            }
            if (!routeOk && interfaceWarning == null) {
                log.warn("Could not determine macOS broadcast route from: {}", output.trim());
            }
        } catch (Exception e) {
            log.warn("Could not check macOS broadcast route: {}", e.getMessage());
        }
    }

    // ── Beat-link initialization ────────────────────────────────────────────

    private void initBeatLink() throws Exception {
        // On macOS with a specified interface, check the 169.254.255.255 broadcast route BEFORE
        // starting beat-link. If it points to the wrong interface, DeviceFinder will never see
        // device announcements and VirtualCdj.start() will time out.
        if (selectedInterface != null && System.getProperty("os.name", "").toLowerCase().contains("mac")) {
            checkBroadcastRoute();
        }

        // Start DeviceFinder
        DeviceFinder.getInstance().start();
        log.info("DeviceFinder started");

        // Configure VirtualCdj
        VirtualCdj.getInstance().setDeviceNumber((byte) playerNumber);
        VirtualCdj.getInstance().setUseStandardPlayerNumber(false);

        // NOTE: beat-link 8.0.0 has NO API to force a specific network interface.
        // VirtualCdj.start() auto-discovers by sending probes to devices found by DeviceFinder.
        // On macOS, the link-local broadcast route (169.254.255.255) must point to the correct
        // interface for this to work. See tools/fix-djlink-route.sh.
        if (selectedInterface != null) {
            log.info("Requested interface {} ({}) — beat-link will auto-discover via DeviceFinder probes",
                selectedInterfaceName, selectedInterfaceAddress);
        }

        if (!VirtualCdj.getInstance().start()) {
            String hint = selectedInterface != null
                ? ". If on macOS, run: sudo route delete 169.254.255.255 && sudo route add -host 169.254.255.255 -interface " + selectedInterfaceName
                : "";
            throw new RuntimeException("VirtualCdj failed to join the Pro DJ Link network (timeout)" + hint);
        }

        // Report which interface beat-link actually chose
        String actualAddr = VirtualCdj.getInstance().getLocalAddress() != null
            ? VirtualCdj.getInstance().getLocalAddress().getHostAddress()
            : "unknown";
        List<NetworkInterface> matched = VirtualCdj.getInstance().getMatchingInterfaces();
        String actualIfaceName = matched != null && !matched.isEmpty()
            ? matched.get(0).getName()
            : "unknown";
        log.info("Joined Pro DJ Link network on {} ({})", actualIfaceName, actualAddr);

        // Layer 3 validation: warn if beat-link chose a different interface than requested
        if (selectedInterface != null && !actualIfaceName.equals(selectedInterfaceName)) {
            interfaceWarning = String.format("Requested interface %s but beat-link bound to %s (%s). "
                + "On macOS, fix with: sudo route delete 169.254.255.255 && sudo route add -host 169.254.255.255 -interface %s",
                selectedInterfaceName, actualIfaceName, actualAddr, selectedInterfaceName);
            log.warn(interfaceWarning);
        }

        // Update reported address/name to what beat-link actually used
        selectedInterfaceAddress = actualAddr;
        if (!actualIfaceName.equals("unknown")) {
            selectedInterfaceName = actualIfaceName;
        }

        // Register all listeners
        registerListeners();

        // Start Finders (metadata, waveform, beatgrid, phrase analysis, art)
        startFinders();

        // Register Finder listeners (metadata, beatgrid, waveform, phrase, cues)
        registerFinderListeners();

        // Emit connected status with interface info
        beatLinkConnected = true;
        int deviceCount = DeviceFinder.getInstance().getCurrentDevices().size();
        emitter.emitBridgeStatus(true, deviceCount, VERSION, null,
            selectedInterfaceName, selectedInterfaceAddress, interfaceCandidates, interfaceWarning);
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
                    emitter.emitBridgeStatus(true, count, VERSION, null,
                        selectedInterfaceName, selectedInterfaceAddress, interfaceCandidates, interfaceWarning);
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
                        emitter.emitBridgeStatus(true, count, VERSION, null,
                            selectedInterfaceName, selectedInterfaceAddress, interfaceCandidates, interfaceWarning);
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

        log.info("Real-time listeners registered (device, player_status, beat)");
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
            log.info("Device {} uses Device Library Plus — Finders will use CrateDigger NFS path", name);
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
        boolean noTrack = status.getTrackType() == CdjStatus.TrackType.NO_TRACK;
        double bpm = noTrack ? 0.0 : status.getEffectiveTempo();
        double pitchPct = noTrack ? 0.0 : ((status.getPitch() / 1048576.0) - 1.0) * 100.0;
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

    // ── Finder lifecycle ────────────────────────────────────────────────────

    private void configureOpusProvider() {
        if (databaseKey != null && !databaseKey.isEmpty()) {
            OpusProvider.getInstance().setDatabaseKey(databaseKey);
            log.info("DLP database key configured — exportLibrary.db decryption enabled");
        }
    }

    private void startFinders() {
        try {
            // Configure DLP database key before starting any Finders
            configureOpusProvider();

            // Start TimeFinder first (required by waveform position tracking)
            TimeFinder.getInstance().start();
            log.info("TimeFinder started");

            // Start MetadataFinder (required by WaveformFinder)
            MetadataFinder.getInstance().start();
            log.info("MetadataFinder started");

            // Start remaining Finders
            BeatGridFinder.getInstance().start();
            log.info("BeatGridFinder started");

            WaveformFinder.getInstance().start();
            log.info("WaveformFinder started");

            AnalysisTagFinder.getInstance().start();
            log.info("AnalysisTagFinder started");

            // Start ArtFinder for album artwork
            ArtFinder.getInstance().start();
            log.info("ArtFinder started");

            log.info("All Finders started successfully");
        } catch (Exception e) {
            log.error("Failed to start Finders: {}. Bridge will continue with real-time data only.", e.getMessage(), e);
        }
    }

    private void registerFinderListeners() {
        // Metadata listener
        MetadataFinder.getInstance().addTrackMetadataListener(update -> {
            try {
                if (update.metadata != null) {
                    emitTrackMetadata(update.player, update.metadata);
                }
            } catch (Exception e) {
                log.error("Error in metadata listener: {}", e.getMessage(), e);
            }
        });

        // Beat grid listener
        BeatGridFinder.getInstance().addBeatGridListener(update -> {
            try {
                if (update.beatGrid != null) {
                    emitBeatGrid(update.player, update.beatGrid);
                }
            } catch (Exception e) {
                log.error("Error in beat grid listener: {}", e.getMessage(), e);
            }
        });

        // Waveform listeners (preview + detail)
        WaveformFinder.getInstance().addWaveformListener(new WaveformListener() {
            @Override
            public void previewChanged(WaveformPreviewUpdate update) {
                try {
                    if (update.preview != null) {
                        emitWaveformPreview(update.player, update.preview);
                    }
                } catch (Exception e) {
                    log.error("Error in waveform preview listener: {}", e.getMessage(), e);
                }
            }
            @Override
            public void detailChanged(WaveformDetailUpdate update) {
                try {
                    if (update.detail != null) {
                        emitWaveformDetail(update.player, update.detail);
                    }
                } catch (Exception e) {
                    log.error("Error in waveform detail listener: {}", e.getMessage(), e);
                }
            }
        });

        // Phrase analysis (PSSI) listener
        AnalysisTagFinder.getInstance().addAnalysisTagListener(
            update -> {
                try {
                    if (update.taggedSection != null) {
                        emitPhraseAnalysis(update.player, update.taggedSection);
                    }
                } catch (Exception e) {
                    log.error("Error in analysis tag listener: {}", e.getMessage(), e);
                }
            },
            ".EXT", "PSSI"
        );

        log.info("Finder listeners registered (metadata, beatgrid, waveform, phrase, cues)");
    }

    // ── Finder emit helpers ───────────────────────────────────────────────

    private void emitTrackMetadata(int player, TrackMetadata metadata) {
        String title = metadata.getTitle() != null ? metadata.getTitle() : "";
        String artist = metadata.getArtist() != null ? metadata.getArtist().label : "";
        String album = metadata.getAlbum() != null ? metadata.getAlbum().label : "";
        String genre = metadata.getGenre() != null ? metadata.getGenre().label : "";
        String key = metadata.getKey() != null ? metadata.getKey().label : "";
        double bpm = metadata.getTempo() / 100.0;
        double duration = metadata.getDuration();
        String color = metadata.getColor() != null ? metadata.getColor().label : null;
        int rating = metadata.getRating();
        String comment = metadata.getComment() != null ? metadata.getComment() : "";
        int rekordboxId = metadata.trackReference != null ? metadata.trackReference.rekordboxId : 0;

        emitter.emitTrackMetadata(player, title, artist, album, genre, key,
            bpm, duration, color, rating, comment, rekordboxId);

        // Also emit cue points from the metadata's cue list
        emitCuePoints(player, metadata);

        log.info("Metadata emitted for player {}: {} — {}", player, title, artist);
    }

    private void emitBeatGrid(int player, BeatGrid beatGrid) {
        List<Map<String, Object>> beats = new ArrayList<>();
        for (int i = 1; i <= beatGrid.beatCount; i++) {
            Map<String, Object> beat = new LinkedHashMap<>();
            beat.put("beat_number", i);
            beat.put("time_ms", (double) beatGrid.getTimeWithinTrack(i));
            beat.put("bpm", (double) beatGrid.getBpm(i) / 100.0);
            beats.add(beat);
        }
        emitter.emitBeatGrid(player, beats);
        log.info("Beat grid emitted for player {}: {} beats", player, beatGrid.beatCount);
    }

    private void emitWaveformPreview(int player, WaveformPreview preview) {
        ByteBuffer data = preview.getData();
        byte[] bytes = new byte[data.remaining()];
        data.duplicate().get(bytes);
        String base64 = Base64.getEncoder().encodeToString(bytes);

        // Get beat count from BeatGridFinder if available
        BeatGrid grid = BeatGridFinder.getInstance().getLatestBeatGridFor(player);
        int totalBeats = grid != null ? grid.beatCount : 0;

        emitter.emitWaveformPreview(player, base64, totalBeats);
        log.info("Waveform preview emitted for player {}: {} bytes", player, bytes.length);
    }

    private void emitWaveformDetail(int player, WaveformDetail detail) {
        ByteBuffer data = detail.getData();
        byte[] bytes = new byte[data.remaining()];
        data.duplicate().get(bytes);
        String base64 = Base64.getEncoder().encodeToString(bytes);

        // Get beat count from BeatGridFinder if available
        BeatGrid grid = BeatGridFinder.getInstance().getLatestBeatGridFor(player);
        int totalBeats = grid != null ? grid.beatCount : 0;

        emitter.emitWaveformDetail(player, base64, totalBeats);
        log.info("Waveform detail emitted for player {}: {} bytes", player, bytes.length);
    }

    private void emitPhraseAnalysis(int player, RekordboxAnlz.TaggedSection section) {
        List<Map<String, Object>> phrases = new ArrayList<>();
        try {
            if (section != null && section.body() instanceof RekordboxAnlz.SongStructureTag) {
                RekordboxAnlz.SongStructureTag ssTag = (RekordboxAnlz.SongStructureTag) section.body();
                RekordboxAnlz.SongStructureBody body = ssTag.body();
                List<RekordboxAnlz.SongStructureEntry> entries = body.entries();
                int moodValue = body.mood() != null ? (int) body.mood().id() : 0;
                for (int i = 0; i < entries.size(); i++) {
                    RekordboxAnlz.SongStructureEntry entry = entries.get(i);
                    int startBeat = entry.beat();
                    int endBeat;
                    if (i + 1 < entries.size()) {
                        endBeat = entries.get(i + 1).beat();
                    } else {
                        // Last entry — use the song structure body's endBeat or beat grid
                        endBeat = body.endBeat();
                        if (endBeat <= startBeat) {
                            BeatGrid grid = BeatGridFinder.getInstance().getLatestBeatGridFor(player);
                            endBeat = grid != null ? grid.beatCount : startBeat + 64;
                        }
                    }

                    // Extract phrase kind name from the kind-specific struct
                    String kindName = getPhraseKindName(entry, body.mood());

                    Map<String, Object> phrase = new LinkedHashMap<>();
                    phrase.put("start_beat", startBeat);
                    phrase.put("end_beat", endBeat);
                    phrase.put("kind", kindName);
                    phrase.put("mood", moodValue);
                    phrases.add(phrase);
                }
            }
        } catch (Exception e) {
            log.error("Error parsing PSSI data for player {}: {}", player, e.getMessage(), e);
        }

        if (!phrases.isEmpty()) {
            emitter.emitPhraseAnalysis(player, phrases);
            log.info("Phrase analysis emitted for player {}: {} phrases", player, phrases.size());
        }
    }

    private String getPhraseKindName(RekordboxAnlz.SongStructureEntry entry, RekordboxAnlz.TrackMood mood) {
        try {
            Object kind = entry.kind();
            if (kind instanceof RekordboxAnlz.PhraseHigh) {
                RekordboxAnlz.MoodHighPhrase id = ((RekordboxAnlz.PhraseHigh) kind).id();
                return id != null ? id.name().toLowerCase() : "unknown";
            } else if (kind instanceof RekordboxAnlz.PhraseMid) {
                RekordboxAnlz.MoodMidPhrase id = ((RekordboxAnlz.PhraseMid) kind).id();
                return id != null ? id.name().toLowerCase() : "unknown";
            } else if (kind instanceof RekordboxAnlz.PhraseLow) {
                RekordboxAnlz.MoodLowPhrase id = ((RekordboxAnlz.PhraseLow) kind).id();
                return id != null ? id.name().toLowerCase() : "unknown";
            }
        } catch (Exception e) {
            log.debug("Could not resolve phrase kind: {}", e.getMessage());
        }
        return "unknown";
    }

    private void emitCuePoints(int player, TrackMetadata metadata) {
        List<Map<String, Object>> cuePoints = new ArrayList<>();
        List<Map<String, Object>> memoryPoints = new ArrayList<>();
        List<Map<String, Object>> hotCues = new ArrayList<>();

        if (metadata.getCueList() != null) {
            for (CueList.Entry cue : metadata.getCueList().entries) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("time_ms", (double) cue.cueTime);
                entry.put("name", cue.comment != null ? cue.comment : "");

                // Determine color
                String color = "";
                if (cue.colorId != 0) {
                    color = String.format("#%06X", cue.colorId & 0xFFFFFF);
                }
                entry.put("color", color);

                if (cue.hotCueNumber > 0) {
                    entry.put("slot", cue.hotCueNumber);
                    hotCues.add(entry);
                } else {
                    memoryPoints.add(entry);
                }
            }
        }

        emitter.emitCuePoints(player, cuePoints, memoryPoints, hotCues);
        log.info("Cue points emitted for player {}: {} memory, {} hot cues",
            player, memoryPoints.size(), hotCues.size());
    }

    /**
     * Clean up beat-link components so we can reinitialize cleanly.
     */
    private void cleanupBeatLink() {
        try { ArtFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { AnalysisTagFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { WaveformFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { BeatGridFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { MetadataFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
        try { TimeFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
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
            // Stop Finders first (reverse of start order)
            try { ArtFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { AnalysisTagFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { WaveformFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { BeatGridFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { MetadataFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
            try { TimeFinder.getInstance().stop(); } catch (Exception e) { /* ignore */ }
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
        String interfaceName = null;
        String databaseKey = null;

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
                case "--interface":
                    if (i + 1 < args.length) interfaceName = args[++i];
                    break;
                case "--database-key":
                    if (i + 1 < args.length) databaseKey = args[++i];
                    break;
                default:
                    System.err.println("Unknown argument: " + args[i]);
                    System.err.println("Usage: java -jar beat-link-bridge.jar [--port N] [--player-number N] [--interface NAME] [--database-key KEY] [--retry-interval S] [--log-level LEVEL]");
                    System.exit(1);
            }
        }

        // Configure SLF4J simple logger
        System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", logLevel.toLowerCase());
        System.setProperty("org.slf4j.simpleLogger.showDateTime", "true");
        System.setProperty("org.slf4j.simpleLogger.dateTimeFormat", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");
        System.setProperty("org.slf4j.simpleLogger.logFile", "System.err");

        BeatLinkBridge bridge = new BeatLinkBridge(port, playerNumber, retryInterval, interfaceName, databaseKey);
        try {
            bridge.start();
        } catch (Exception e) {
            log.error("Fatal error: {}", e.getMessage(), e);
            System.exit(1);
        }
    }
}
