from __future__ import annotations

import string
from typing import Optional

from .pak import PakArchive, PakEntry


def archive_summary(archive: PakArchive) -> str:
    compressed = sum(1 for entry in archive.entries if entry.is_compressed)
    total_size = sum(entry.display_size for entry in archive.entries)
    lines = [
        str(archive.path),
        "",
        "Files: %d" % len(archive.entries),
        "Compressed files: %d" % compressed,
        "Unpacked size: %s" % format_size(total_size),
        "DATA chunk size: %s" % format_size(archive.data_size),
        "FILE table size: %s" % format_size(archive.entries_size),
    ]
    return "\n".join(lines)


def entry_preview(entry: PakEntry) -> str:
    header = [
        entry.name,
        "Size: %s" % format_size(entry.display_size),
        "Packed size: %s" % format_size(entry.size),
        "Compression: %s" % entry.compression_label,
        "",
    ]

    text = decode_text(entry.data)
    if text is not None:
        return "\n".join(header) + text

    preview = entry.data[:4096]
    return "\n".join(header) + "Binary preview, first %d bytes:\n\n%s" % (
        len(preview),
        hexdump(preview),
    )


def decode_text(data: bytes) -> Optional[str]:
    if not data:
        return ""

    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue

        if "\x00" in text[:200]:
            continue

        control_count = sum(1 for char in text[:1000] if _is_unfriendly_control(char))
        if control_count <= max(4, len(text[:1000]) // 20):
            return text

    return None


def hexdump(data: bytes) -> str:
    if not data:
        return ""

    rows = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part = " ".join("%02X" % byte for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        rows.append("%08X  %-47s  %s" % (offset, hex_part, ascii_part))
    return "\n".join(rows)


def format_size(size: int) -> str:
    value = float(size)
    for suffix in ("B", "KB", "MB", "GB"):
        if value < 1024 or suffix == "GB":
            if suffix == "B":
                return "%d B" % size
            return "%.1f %s" % (value, suffix)
        value /= 1024
    return "%d B" % size


def _is_unfriendly_control(char: str) -> bool:
    if char in "\r\n\t":
        return False
    return char not in string.printable and ord(char) < 32
