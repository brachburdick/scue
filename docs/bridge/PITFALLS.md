# Bridge Pitfalls & Library-Specific Findings

Hard-won discoveries from building the SCUE bridge system. Each entry documents
behavior that is **not obvious from documentation** and would cause bugs if not
known in advance. Organized by technology.

---

## beat-link (Java, v8.0.0)

### MetadataFinder returns wrong records on Device Library Plus hardware (RESOLVED in 8.1.0)

**Affects:** XDJ-AZ, Opus Quad, OMNIS-DUO, CDJ-3000X (beat-link 8.0.0 only)

beat-link 8.0.0's `MetadataFinder` and `CrateDigger` query track metadata using
DeviceSQL IDs. Device Library Plus (DLP) hardware uses a different ID namespace
(`exportLibrary.db` DLP IDs). When `MetadataFinder` uses a DLP ID to query
DeviceSQL data, it retrieves the **wrong record** -- a different track entirely.

**Resolution (ADR-017):** beat-link 8.1.0-SNAPSHOT has native XDJ-AZ support.
CrateDigger downloads `exportLibrary.db` over NFS, providing ID translation.
All Finders work correctly on XDJ-AZ. The bridge now uses 8.1.0-SNAPSHOT with
all Finders enabled. ADR-012's blanket disabling is superseded.

**Still affected:** Opus Quad has no dbserver — still requires metadata archives or
rbox/pyrekordbox USB scanning.

**Detection:** The bridge detects DLP hardware by matching `DeviceAnnouncement.getDeviceName()`
(lowercased, normalized) against known models: `xdj-az`, `opus-quad`, `omnis-duo`, `cdj-3000x`.
Reports `uses_dlp: true` in the `device_found` message.


### Database key required for DLP database decryption

**Affects:** XDJ-AZ, Opus Quad, and other DLP hardware

`exportLibrary.db` is encrypted. `OpusProvider.setDatabaseKey()` must be called
before Finders start, or CrateDigger cannot read the database. The bridge accepts
`--database-key <KEY>` on the command line. The Python side passes this via the
`SCUE_DLP_DATABASE_KEY` environment variable.

Without the key, Finders will start but fail to resolve metadata for DLP devices.
Real-time data (BPM, pitch, beat, on-air) will still work.


### beat-link has NO API to force a specific network interface

`VirtualCdj.getInstance().start()` auto-discovers the network by sending probes
to devices found by `DeviceFinder`. There is **no** `setInterface()` or similar
method in beat-link 8.0.0 to force a specific NIC.

On macOS, the OS-level broadcast route for `169.254.255.255` determines which
interface receives link-local broadcasts. If this route points to the wrong
interface (common -- macOS assigns it to whichever link-local interface registers
first, often Wi-Fi), `DeviceFinder` never sees device announcements and
`VirtualCdj.start()` silently times out with no error.

**Solution:** Fix the OS route before starting the bridge:
```bash
sudo route delete 169.254.255.255
sudo route add -host 169.254.255.255 -interface en16
```
The bridge checks this route on startup (`route get 169.254.255.255`) and emits
a warning with the fix command if it points to the wrong interface. The route
does **not** persist across reboots.


### XDJ-AZ track changes: trackType does NOT transition through NO_TRACK

On legacy CDJs, loading a new track causes `CdjStatus.getTrackType()` to
transition: `REKORDBOX -> NO_TRACK -> REKORDBOX`. Code that watches for a
`NO_TRACK` transition to detect track changes will never fire on the XDJ-AZ.

On the XDJ-AZ, `trackType` stays as `REKORDBOX` during track loads. The only
reliable signal is `CdjStatus.getRekordboxId()` changing value.

**Solution:** Detect track changes by monitoring `rekordboxId` for value changes.
Even though the ID is unreliable for metadata lookup via beat-link (DLP namespace
issue), a **change** in ID reliably indicates a new track was loaded. Use multiple
signals for robustness: rekordbox ID change OR trackType transition OR significant
BPM change at same pitch.


### rekordbox_id instability between play states on XDJ-AZ

`CdjStatus.getRekordboxId()` can return different values for the **same track**
when toggling between paused and playing states on the XDJ-AZ. The Python adapter
handles this by only firing `on_track_loaded` when the ID changes to a **nonzero**
value different from the current one. Zero IDs are ignored (track unload).


### Pitch value is nonsensical when no track is loaded

`CdjStatus.getPitch()` returns a garbage value when `getTrackType() == NO_TRACK`.
Always guard pitch calculations with a no-track check:

```java
double pitchPct = noTrack ? 0.0 : ((status.getPitch() / 1048576.0) - 1.0) * 100.0;
```

Similarly guard BPM: `double bpm = noTrack ? 0.0 : status.getEffectiveTempo();`


### is_on_air requires BOTH channel fader AND master knob

`CdjStatus.isOnAir()` returns `true` only when the channel fader is up **AND**
the master output knob is not fully off. Testing with fader up but master down
will show `is_on_air: false`.


### Shutdown must call VirtualCdj.stop() or phantom devices appear

If the bridge process exits without calling `VirtualCdj.getInstance().stop()`,
Pioneer hardware displays a phantom device (the bridge's claimed player number)
for up to 30 seconds. Always use a JVM shutdown hook:

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    BeatFinder.getInstance().stop();
    VirtualCdj.getInstance().stop();  // Announces departure from network
    DeviceFinder.getInstance().stop();
}));
```

---

## rbox (Python, v0.1.7) -- Rust-backed Pioneer library

### Rust ANLZ parser panics on DLP ANLZ files (CRITICAL)

`rbox.Anlz(path)` causes a Rust `panic!()` on certain ANLZ files from XDJ-AZ USB
exports. A Rust panic **kills the entire Python process** -- it is not a catchable
Python exception. The panic occurs when the Rust parser hits unknown section
variants in DLP-format ANLZ files:

```
thread '<unnamed>' panicked at rbox/src/anlz/anlz.rs:1427:46:
Can't read ANLZ:
  Error: no variants matched at 0x722
    While parsing field 'self_0' in Content::BeatGrid
      Error: assertion failed: `u2 == 0x80000` at 0x722
```

Not all files fail -- the panic is unpredictable. Of 2,022 ANLZ files from a
real XDJ-AZ USB, 4 trigger the panic.

**Solution (ADR-013):** Never use rbox for ANLZ parsing. Use the two-tier
pure-Python strategy instead (pyrekordbox primary, custom parser fallback).
rbox is retained **only** for `exportLibrary.db` reading via `OneLibrary`, which
works correctly and does not panic.

**General rule:** Never use Rust-backed parsers for untrusted binary formats
without subprocess isolation. Pure Python is slower but cannot abort the process.


### rbox OneLibrary is the only Python library for DLP USB databases

pyrekordbox's `Rekordbox6Database` targets the **desktop** `master.db`, not the
USB `exportLibrary.db`. rbox's `OneLibrary` is currently the only Python library
that reads the DLP/OneLibrary USB database format. This is why rbox is retained
despite the ANLZ panic issue.

```python
from rbox import OneLibrary
db = OneLibrary("/path/to/PIONEER/rekordbox/exportLibrary.db")
contents = db.get_contents()  # All tracks
```

Key fields: `content.id` (rekordbox DLP ID), `content.title`, `content.artist_id`,
`content.bpmx100` (BPM * 100), `content.key_id`, `content.path`,
`content.analysis_data_file_path` (ANLZ path).

Artist and key names require separate lookups:
```python
artist = db.get_artist_by_id(content.artist_id)
key = db.get_key_by_id(content.key_id)
```

---

## pyrekordbox (Python, v0.4.4+) -- Pure Python Pioneer library

### get() vs get_tag() return completely different types

`AnlzFile` has two accessor APIs that look similar but return **different types**:

| Method | Returns | Use for |
|--------|---------|---------|
| `anlz.get("beat_grid")` | Tuple of 3 numpy arrays: `(beat_numbers, tempos_bpm, times_seconds)` | Bulk numerical analysis |
| `anlz.get_tag("beat_grid")` | `PQTZAnlzTag` object with `.content.entries` | Per-entry structured access |

Using `get()` and then trying `.content.entries` on the result causes:
`AttributeError: 'tuple' object has no attribute 'content'`

**Always use `get_tag()` when you need structured entry access.**


### get_tag() entry field units are format-native, not normalized

`get_tag("beat_grid")` returns entries where:
- `entry.tempo` = BPM * 100 (integer, e.g., 12800 = 128.00 BPM)
- `entry.time` = milliseconds (integer, e.g., 500 = 0.5 seconds)
- `entry.beat` = beat number within bar (1-4 cycling)

This matches the raw ANLZ binary format. The `get()` tuple API normalizes
differently (tempos in BPM, times in seconds). Do not mix assumptions between
the two APIs.


### PCOB cue_type is a string, not an integer

```python
for tag in anlz.getall_tags("PCOB"):
    tag.content.cue_type   # "hotcue" or "memory" (string, NOT int 0/1)
    tag.content.entries     # list of cue entries
```

Each cue entry:
```python
entry.hot_cue    # int: slot number (1-8 for hot cues)
entry.time       # int: milliseconds
entry.type       # "single" or "loop" (string, NOT int 1/2)
entry.status     # "enabled" or "disabled" (string)
entry.loop_time  # int: loop end time in ms (0xFFFFFFFF if not a loop)
```

Code that checks `cue_type == 1` or `entry.type == 1` will silently fail
(always False). Use string comparison: `cue_type == "hotcue"`, `entry.type == "loop"`.


### getall_tags("PCOB") returns 2 tags per file

Every ANLZ file with cues contains exactly 2 PCOB sections: one with
`cue_type="hotcue"` and one with `cue_type="memory"`. Either may have an empty
`entries` list. Always iterate both.


### 4 out of 2,022 real ANLZ files fail parsing

pyrekordbox raises assertion errors on a small number of DLP ANLZ files:
```
Error in path (parsing) -> content -> u2
parsing expected 524288 but parsed 588988
```

These are files with non-standard section variants that violate pyrekordbox's
strict field assertions. The files are valid enough to read with a lenient parser.

**Solution:** The custom `anlz_parser.py` fallback (Tier 2) handles these files
by reading only the PQTZ and PCOB sections and skipping everything else. Of the 4
failing files in testing, all 4 were successfully parsed by the custom fallback,
recovering 149-284 beats each.

---

## ANLZ Binary Format -- Key Structural Details

### PMAI file header: field1 is header_len, field2 is file_len

The PMAI (file-level) header is:
```
Offset  Size  Field
0x00    4     Tag: "PMAI" (ASCII)
0x04    4     header_len (big-endian u32) -- typically 28
0x08    4     file_len (big-endian u32) -- total file size (e.g., 7090)
0x0C    16    Unknown/reserved padding
```

**Critical bug pattern:** Reading field2 as the header length causes the parser
to skip the entire file (offset jumps to byte 7090 instead of byte 28). Test
data that uses `header_len == file_len` (e.g., both 28) will **mask this bug**.

Always construct test ANLZ data with `header_len != file_len`:
```python
# CORRECT test header -- catches the bug
struct.pack(">4sII", b"PMAI", 28, 4096) + b"\x00" * 16

# WRONG test header -- masks the bug (both values equal)
struct.pack(">4sII", b"PMAI", 28, 28) + b"\x00" * 16
```

### Section headers follow the same pattern

Every section after PMAI uses the same tag-length-value layout:
```
Offset  Size  Field
0x00    4     Tag (ASCII, e.g., "PQTZ", "PCOB", "PPTH")
0x04    4     header_len (big-endian u32)
0x08    4     total_len (big-endian u32) -- header + body
```

`total_len` is used to skip to the next section: `offset += total_len`.

### PQTZ beat grid entry layout (16 bytes each)

```
Offset  Size  Field
0x00    2     beat_number (u16) -- 1-4 cycling
0x02    2     tempo (u16) -- BPM * 100
0x04    4     time_ms (u32) -- milliseconds from track start
0x08    8     padding (zeros)
```

Entry count is at PQTZ header offset 0x14 (after tag + header_len + total_len +
two unknown u32 fields).

### PCPT cue entry layout (56 bytes each, inside PCOB)

```
Offset  Size  Field
0x00    4     Tag: "PCPT"
0x04    4     header_len (24 or 28)
0x08    4     total_len (56)
0x0C    4     hot_cue slot (u32, 1-8 for hot cues, 0 for memory)
0x10    4     status (u32, 4=enabled)
0x14    4     u1 (u32, typically 0x10000)
0x18    2     order_first (u16)
0x1A    2     order_last (u16)
0x1C    1     cue_point_type (u8, 1=single, 2=loop)
0x1D    1     padding
0x1E    2     u2 (u16)
0x20    4     time_ms (u32)
0x24    4     loop_time_ms (u32, 0xFFFFFFFF if not loop)
0x28    16    padding
```

---

## macOS Networking

### Broadcast UDP requires IP_BOUND_IF, not unicast bind

On macOS, binding a UDP socket to a unicast IP address (e.g., `169.254.20.47`)
does **not** receive broadcast packets from that interface. The kernel silently
drops them. Pioneer hardware broadcasts keepalives and status packets to the
subnet broadcast address.

**Solution:** Bind to `""` (INADDR_ANY / `0.0.0.0`) and use
`setsockopt(IPPROTO_IP, IP_BOUND_IF=25, socket.if_nametoindex(iface_name))`
to lock the socket to the specific interface.

```python
IP_BOUND_IF = 25
if_idx = socket.if_nametoindex(iface_name)
sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, if_idx)
sock.bind(("", port))
```

On Linux, use `SO_BINDTODEVICE` instead:
```python
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, (iface_name + "\x00").encode())
```


### Link-local broadcast route does not persist across reboots

The `route add` fix for `169.254.255.255` is lost on every macOS reboot and
every cable change. The bridge checks the route on startup and warns if wrong,
but cannot fix it without `sudo` access.

The helper script `tools/fix-djlink-route.sh <interface>` automates the fix.
Must be run with `sudo` after every reboot or cable reconnection.
