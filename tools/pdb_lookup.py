"""Quick export.pdb parser — extracts track ID → title mapping.

Usage:
    python tools/pdb_lookup.py <path_to_export.pdb> [--id N]

Without --id: prints all tracks.
With --id N: prints only the track with rekordbox ID N.
"""

import struct
import sys
from pathlib import Path

# Track rows have an 8-byte row header before the DeviceSQL track structure.
ROW_HEADER_SIZE = 8


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_devicesql_string(data: bytes, offset: int) -> str:
    """Read a DeviceSQL string at the given offset."""
    if offset >= len(data) - 1:
        return ""

    flag = data[offset]

    # Short string (bit 0 set): length in upper bits, data follows flag byte.
    # Flag 0x91 = short UTF-16LE, flag 0x41 = short ASCII, etc.
    if flag & 0x01:
        length = flag >> 1
        raw = data[offset + 1 : offset + 1 + length]
        # If flag has bit 4 set (0x10), it's UTF-16LE
        if flag & 0x10:
            return raw.decode("utf-16-le", errors="replace").rstrip("\x00")
        return raw.decode("ascii", errors="replace").rstrip("\x00")

    # Long string: 1 byte flag + 2 bytes length + 1 byte pad + data
    if offset + 4 > len(data):
        return ""

    total_len = read_u16(data, offset + 1)
    if total_len < 4:
        return ""

    str_data = data[offset + 4 : offset + total_len]

    if flag & 0x10:  # UTF-16LE (0x90, 0xB0, etc.)
        return str_data.decode("utf-16-le", errors="replace").rstrip("\x00")
    else:  # ASCII/UTF-8 (0x40, 0x60, etc.)
        return str_data.decode("utf-8", errors="replace").rstrip("\x00")


def parse_tracks(pdb_path: str) -> dict[int, dict]:
    """Parse export.pdb and return {rekordbox_id: {title, artist_id, ...}}."""
    data = Path(pdb_path).read_bytes()

    page_size = read_u32(data, 4)
    num_tables = read_u32(data, 8)

    # Find tracks table (type 0)
    tracks_first_page = None
    tracks_last_page = None

    for i in range(num_tables):
        tp_offset = 12 + i * 16
        ttype = read_u32(data, tp_offset)
        first_page = read_u32(data, tp_offset + 8)
        last_page = read_u32(data, tp_offset + 12)
        if ttype == 0:
            tracks_first_page = first_page
            tracks_last_page = last_page
            break

    if tracks_first_page is None:
        print("ERROR: No tracks table found")
        return {}

    tracks = {}
    page_idx = tracks_first_page
    visited = set()

    while page_idx not in visited:
        visited.add(page_idx)
        page_offset = page_size * page_idx

        if page_offset + page_size > len(data):
            break

        # Page header
        page_flags = data[page_offset + 0x1B]
        next_page = read_u32(data, page_offset + 0x0C)

        # Only process data pages (not index pages — flag bit 6 set)
        if page_flags & 0x40:
            page_idx = next_page
            continue

        # Row counts: 3 bytes at offset 0x18
        rc_bytes = data[page_offset + 0x18 : page_offset + 0x1B]
        rc_val = rc_bytes[0] | (rc_bytes[1] << 8) | (rc_bytes[2] << 16)
        num_row_offsets = rc_val & 0x1FFF  # bits 0-12

        if num_row_offsets == 0:
            page_idx = next_page
            continue

        # Row index grows backward from end of page.
        # Layout per group (up to 16 rows):
        #   [row_offset_N-1 (2b)] ... [row_offset_0 (2b)] [presence (2b)] [unknown (2b)]
        # The last 2 bytes of the page are an unknown/txn field,
        # presence bitmask is at page_end - 4.
        page_end = page_offset + page_size

        rows_remaining = num_row_offsets
        group_end = page_end  # pointer to current group's end

        while rows_remaining > 0:
            group_size = min(rows_remaining, 16)

            # Read presence at group_end - 4 (skip 2-byte unknown at group_end - 2)
            presence = read_u16(data, group_end - 4)

            # Row offsets start at group_end - 6, growing backward
            for bit in range(group_size):
                ofs_addr = group_end - 6 - (bit * 2)
                if ofs_addr < page_offset + 0x20:
                    break

                if not (presence & (1 << bit)):
                    continue

                row_ofs = read_u16(data, ofs_addr)
                row_addr = page_offset + 0x20 + row_ofs
                # Track data starts after 8-byte row header
                track_base = row_addr + ROW_HEADER_SIZE

                if track_base + 0x88 > page_offset + page_size:
                    continue

                try:
                    track_id = read_u32(data, track_base + 0x48)
                    artist_id = read_u32(data, track_base + 0x44)
                    tempo_raw = read_u32(data, track_base + 0x38)
                    bpm = tempo_raw / 100.0

                    # Title: string offset index 17
                    title_ofs = read_u16(data, track_base + 0x5E + 17 * 2)
                    title = read_devicesql_string(data, track_base + title_ofs)

                    # File path: string offset index 20
                    fp_ofs = read_u16(data, track_base + 0x5E + 20 * 2)
                    file_path = read_devicesql_string(data, track_base + fp_ofs)

                    # Keep latest version (PDB may have duplicate IDs — last wins)
                    tracks[track_id] = {
                        "title": title,
                        "artist_id": artist_id,
                        "bpm": bpm,
                        "file_path": file_path,
                    }
                except Exception:
                    pass  # Skip malformed rows

            # Move to next group
            group_end -= 4 + (group_size * 2)
            rows_remaining -= group_size

        page_idx = next_page

    return tracks


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/pdb_lookup.py <export.pdb> [--id N] [--search TEXT]")
        sys.exit(1)

    pdb_path = sys.argv[1]
    target_id = None
    search_text = None

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--id" and i + 1 < len(sys.argv):
            target_id = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--search" and i + 1 < len(sys.argv):
            search_text = sys.argv[i + 1].lower()
            i += 2
        else:
            i += 1

    tracks = parse_tracks(pdb_path)
    print(f"Parsed {len(tracks)} tracks from {pdb_path}\n")

    if target_id is not None:
        if target_id in tracks:
            t = tracks[target_id]
            print(f"  ID {target_id}: {t['title']}")
            print(f"    BPM: {t['bpm']:.2f}")
            print(f"    File: {t['file_path']}")
        else:
            print(f"  ID {target_id}: NOT FOUND")
            # Show nearby IDs
            nearby = sorted(tracks.keys(), key=lambda x: abs(x - target_id))[:5]
            print(f"  Closest IDs: {nearby}")
    elif search_text is not None:
        matches = [(tid, t) for tid, t in tracks.items() if search_text in t["title"].lower()]
        print(f"Found {len(matches)} matches for '{search_text}':\n")
        for tid, t in sorted(matches, key=lambda x: x[0]):
            print(f"  ID {tid}: {t['title']} (BPM {t['bpm']:.1f})")
    else:
        for tid, t in sorted(tracks.items()):
            print(f"  ID {tid}: {t['title']} (BPM {t['bpm']:.1f})")


if __name__ == "__main__":
    main()
