# Beat-Link-Trigger Configuration for SCUE

## Overview

SCUE receives real-time Pioneer DJ data via OSC messages from beat-link-trigger.
You need to set up **two triggers** in beat-link-trigger (one per deck/channel).

## Setup

### 1. Open beat-link-trigger

Make sure beat-link-trigger is running and connected to your Pioneer gear
(it should discover devices on the same network — you're connected via USB-CAT5).

### 2. Create Trigger for Channel 1

1. Click **+** to add a new trigger
2. Set **Watch** to: `Player 1` (or whatever your left deck is)
3. Set **Message** to: `Custom`
4. Set **Enabled** to: `Always`

Click **Expressions** (the gear icon) and paste these:

#### Setup Expression
```clojure
(swap! locals assoc :osc-client (osc/osc-client "localhost" 9000))
```

#### Tracked Update Expression
```clojure
(let [client (:osc-client @locals)
      ch     1
      prefix (str "/deck/" ch "/")]
  ;; Playing state
  (osc/osc-send client (str prefix "playing") (if (.isPlaying status) 1.0 0.0))
  (osc/osc-send client (str prefix "on_air") (if (.isOnAir status) 1.0 0.0))
  (osc/osc-send client (str prefix "synced") (if (.isSynced status) 1.0 0.0))
  (osc/osc-send client (str prefix "master") (if (.isTempoMaster status) 1.0 0.0))

  ;; BPM
  (osc/osc-send client (str prefix "original_bpm") (float (/ (.getBpm status) 100.0)))
  (osc/osc-send client (str prefix "effective_bpm") (float effective-tempo))
  (osc/osc-send client (str prefix "pitch_percent") (float (* (- pitch-multiplier 1.0) 100.0)))

  ;; Position
  (osc/osc-send client (str prefix "beat_number") (int (max 0 (.getBeatNumber status))))
  (osc/osc-send client (str prefix "beat_within_bar") (int (max 0 (.getBeatWithinBar status))))
  (osc/osc-send client (str prefix "position_ms")
    (float (if (.isTrackLoaded status)
             (* (.getBeatNumber status) (/ 60000.0 (max 1.0 effective-tempo)))
             0.0)))

  ;; Track metadata (only send when available)
  (when track-title
    (osc/osc-send client (str prefix "track_title") (str track-title)))
  (when track-artist
    (osc/osc-send client (str prefix "track_artist") (str track-artist)))
  (when track-key
    (osc/osc-send client (str prefix "track_key") (str track-key)))
  (when track-genre
    (osc/osc-send client (str prefix "track_genre") (str track-genre)))
  (when track-length
    (osc/osc-send client (str prefix "track_length") (float track-length)))
  (when (.getRekordboxId status)
    (osc/osc-send client (str prefix "rekordbox_id") (int (.getRekordboxId status)))))
```

#### Beat Expression
```clojure
(let [client (:osc-client @locals)]
  (osc/osc-send client "/deck/1/beat" (int beat-within-bar)))
```

#### Shutdown Expression
```clojure
(osc/osc-close (:osc-client @locals))
```

### 3. Create Trigger for Channel 2

Repeat the same steps but:
1. Set **Watch** to: `Player 2`
2. Change all occurrences of `ch 1` to `ch 2` in the Tracked Update Expression:
   ```clojure
   ch     2
   ```
3. Change the Beat Expression to use `/deck/2/beat`:
   ```clojure
   (osc/osc-send client "/deck/2/beat" (int beat-within-bar))
   ```

### 4. Verify

1. Start SCUE: `uvicorn app:app --reload --port 8000`
2. Open `http://localhost:8000` in your browser
3. The "Pioneer: Connected" badge should appear in the header (this means the
   WebSocket is connected — OSC data will flow when beats start)
4. Load a track on your CDJ and press play
5. You should see the deck panel update in real-time

## OSC Message Reference

All messages use the pattern `/deck/{channel}/{field}`:

| Address | Type | Description |
|---------|------|-------------|
| `/deck/1/playing` | float (0/1) | Play state |
| `/deck/1/on_air` | float (0/1) | Channel fader up on mixer |
| `/deck/1/synced` | float (0/1) | Sync enabled |
| `/deck/1/master` | float (0/1) | Tempo master |
| `/deck/1/original_bpm` | float | Track's native BPM |
| `/deck/1/effective_bpm` | float | BPM adjusted for pitch |
| `/deck/1/pitch_percent` | float | Pitch fader as percentage |
| `/deck/1/beat_number` | int | Absolute beat count |
| `/deck/1/beat_within_bar` | int | 1-4 position in measure |
| `/deck/1/position_ms` | float | Estimated playback position |
| `/deck/1/track_title` | string | Track title from rekordbox |
| `/deck/1/track_artist` | string | Artist name |
| `/deck/1/track_key` | string | Musical key |
| `/deck/1/track_genre` | string | Genre tag |
| `/deck/1/track_length` | float | Track duration in seconds |
| `/deck/1/rekordbox_id` | int | Rekordbox database ID |
| `/deck/1/beat` | int | Beat-within-bar (from beat expression) |

## Troubleshooting

- **No data appearing**: Make sure beat-link-trigger shows "Online" and your
  player appears in the Trigger's watch dropdown
- **OSC port conflict**: If port 9000 is in use, change it in both
  the Setup Expression (`osc-client "localhost" 9000`) and in
  `pioneer/osc_receiver.py` (`OSC_PORT = 9000`)
- **Metadata missing**: Track metadata requires that beat-link-trigger has
  successfully loaded the rekordbox database from the USB/SD card. Make sure
  "Request Track Metadata" is checked in the beat-link-trigger preferences.
