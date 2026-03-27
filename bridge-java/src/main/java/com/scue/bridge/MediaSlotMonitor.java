package com.scue.bridge;

import org.deepsymmetry.beatlink.*;
import org.deepsymmetry.beatlink.data.*;
import org.deepsymmetry.beatlink.dbserver.ConnectionManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.*;

/**
 * Monitors media slot changes (USB/SD mount/unmount) on Pioneer hardware.
 *
 * XDJ-AZ and other all-in-one units do NOT send unsolicited media broadcast packets,
 * so passive MountListener alone is insufficient. This monitor uses two strategies:
 *
 *   1. Active polling: periodically calls VirtualCdj.sendMediaQuery() for each known
 *      player's USB and SD slots. When MetadataFinder processes the response, it fires
 *      MountListener callbacks.
 *
 *   2. Passive MountListener: registered on MetadataFinder for standalone CDJs that DO
 *      send unsolicited media broadcasts.
 *
 * On unmount: emits media_change WS message, restarts ConnectionManager to clear stale
 * dbserver sessions (prevents the crash-on-reinsertion bug).
 *
 * On mount: emits media_change WS message with media details if available.
 */
public class MediaSlotMonitor implements MountListener {

    private static final Logger log = LoggerFactory.getLogger(MediaSlotMonitor.class);

    /** Polling interval for active media queries. */
    private static final long POLL_INTERVAL_MS = 2000;

    private final MessageEmitter emitter;
    private final ScheduledExecutorService scheduler;

    /** Tracks which slots we know are mounted — prevents duplicate events. */
    private final Set<SlotReference> mountedSlots = ConcurrentHashMap.newKeySet();

    /** Players we're aware of (from DeviceFinder). */
    private final Set<Integer> knownPlayers = ConcurrentHashMap.newKeySet();

    private volatile boolean running = false;

    public MediaSlotMonitor(MessageEmitter emitter) {
        this.emitter = emitter;
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "media-slot-monitor");
            t.setDaemon(true);
            return t;
        });
    }

    /**
     * Start monitoring. Registers MountListener on MetadataFinder and begins
     * active polling for all-in-one units.
     */
    public void start() {
        if (running) return;
        running = true;

        // Register passive MountListener
        if (MetadataFinder.getInstance().isRunning()) {
            MetadataFinder.getInstance().addMountListener(this);
            log.info("MountListener registered on MetadataFinder");

            // Seed mounted slots from MetadataFinder's current state
            for (SlotReference slot : MetadataFinder.getInstance().getMountedMediaSlots()) {
                mountedSlots.add(slot);
                log.info("Initial mounted slot: player {} {}", slot.player, slotName(slot));
            }
        }

        // Start active polling (covers XDJ-AZ and other all-in-ones)
        scheduler.scheduleAtFixedRate(this::pollMediaSlots, POLL_INTERVAL_MS, POLL_INTERVAL_MS,
            TimeUnit.MILLISECONDS);
        log.info("Media slot polling started (interval={}ms)", POLL_INTERVAL_MS);
    }

    /**
     * Stop monitoring and clean up.
     */
    public void stop() {
        running = false;
        scheduler.shutdownNow();
        if (MetadataFinder.getInstance().isRunning()) {
            MetadataFinder.getInstance().removeMountListener(this);
        }
        mountedSlots.clear();
        knownPlayers.clear();
        log.info("Media slot monitor stopped");
    }

    /**
     * Notify the monitor of a discovered player. Called from DeviceFinder listener.
     */
    public void addPlayer(int playerNumber) {
        knownPlayers.add(playerNumber);
    }

    /**
     * Notify the monitor that a player was lost. Called from DeviceFinder listener.
     */
    public void removePlayer(int playerNumber) {
        knownPlayers.remove(playerNumber);
        // Clean up slot tracking for this player
        mountedSlots.removeIf(slot -> slot.player == playerNumber);
    }

    // ── MountListener implementation (passive path) ─────────────────────────

    @Override
    public void mediaMounted(SlotReference slot) {
        if (!running) return;
        if (mountedSlots.add(slot)) {
            // Newly mounted — emit event
            String name = slotName(slot);
            MediaDetails details = MetadataFinder.getInstance().getMediaDetailsFor(slot);
            String mediaName = details != null ? details.name : null;
            int trackCount = details != null ? details.trackCount : -1;

            emitter.emitMediaChange(slot.player, name, "mounted", mediaName, trackCount);
            log.info("Media mounted: player {} slot {} (name={}, tracks={})",
                slot.player, name, mediaName, trackCount);
        }
    }

    @Override
    public void mediaUnmounted(SlotReference slot) {
        if (!running) return;
        if (mountedSlots.remove(slot)) {
            String name = slotName(slot);
            emitter.emitMediaChange(slot.player, name, "unmounted", null, -1);
            log.info("Media unmounted: player {} slot {}", slot.player, name);

            // Restart ConnectionManager to clear stale dbserver sessions.
            // This prevents the crash-on-reinsertion bug where beat-link tries to
            // use a stale NFS/dbserver connection for the re-mounted media.
            refreshConnectionManager();
        }
    }

    // ── Active polling (for all-in-one units like XDJ-AZ) ───────────────────

    private void pollMediaSlots() {
        if (!running || !VirtualCdj.getInstance().isRunning()) return;

        for (int player : knownPlayers) {
            // Only poll player-range devices (1-6), not mixers (33+)
            if (player > 6) continue;

            pollSlot(player, CdjStatus.TrackSourceSlot.USB_SLOT);
            pollSlot(player, CdjStatus.TrackSourceSlot.SD_SLOT);
        }
    }

    private void pollSlot(int player, CdjStatus.TrackSourceSlot slotType) {
        try {
            SlotReference slotRef = SlotReference.getSlotReference(player, slotType);
            VirtualCdj.getInstance().sendMediaQuery(slotRef);
            // Response is processed asynchronously by MetadataFinder, which will
            // fire mediaMounted/mediaUnmounted callbacks on this listener.
        } catch (java.io.IOException e) {
            // Expected when player is not reachable (powered off, network issue)
            log.debug("Media query failed for player {} {}: {}", player, slotType, e.getMessage());
        } catch (Exception e) {
            log.warn("Unexpected error polling media slot player {} {}: {}",
                player, slotType, e.getMessage());
        }
    }

    // ── DLP session recovery ────────────────────────────────────────────────

    /**
     * Restart ConnectionManager to clear stale dbserver sessions.
     * This is fast (~100ms) and recovers DLP for all slots on the player.
     * Idle connections time out in 1s anyway, so impact is minimal.
     */
    private void refreshConnectionManager() {
        try {
            if (ConnectionManager.getInstance().isRunning()) {
                log.info("Refreshing ConnectionManager to clear stale DLP sessions...");
                ConnectionManager.getInstance().stop();
                ConnectionManager.getInstance().start();
                log.info("ConnectionManager refreshed successfully");
            }
        } catch (Exception e) {
            log.error("Failed to refresh ConnectionManager: {}", e.getMessage(), e);
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────────

    private static String slotName(SlotReference slot) {
        switch (slot.slot) {
            case USB_SLOT: return "usb";
            case SD_SLOT: return "sd";
            default: return slot.slot.name().toLowerCase();
        }
    }
}
