from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, Iterable, List, Sequence, Tuple, Union


ENTRY_DIRECTORY = 0
ENTRY_FILE = 1
COMPRESSION_NONE = 0
COMPRESSION_ZLIB = 0x106


class PakFormatError(ValueError):
    """Raised when a file does not match the expected PAC1 container layout."""


@dataclass
class PakEntry:
    name: str
    binary_offset: int
    size: int
    original_size: int
    compression_type: int
    unknown_data: bytes = field(repr=False)
    data: bytes = field(default=b"", repr=False)

    @property
    def is_compressed(self) -> bool:
        return self.compression_type == COMPRESSION_ZLIB

    @property
    def display_size(self) -> int:
        if self.original_size:
            return self.original_size
        return len(self.data) if self.data else self.size

    @property
    def compression_label(self) -> str:
        if self.compression_type == COMPRESSION_NONE:
            return "none"
        if self.compression_type == COMPRESSION_ZLIB:
            return "zlib"
        return "unknown 0x%X" % self.compression_type


@dataclass
class PakArchive:
    path: Path
    entries: List[PakEntry]
    form_size: int
    data_size: int
    entries_size: int

    @classmethod
    def open(cls, path: Union[str, Path]) -> "PakArchive":
        archive_path = Path(path)
        with archive_path.open("rb") as handle:
            return cls._read(handle, archive_path)

    @classmethod
    def _read(cls, handle: BinaryIO, path: Path) -> "PakArchive":
        form_size = _read_form(handle)
        _read_head(handle)
        data_size = _read_data_header_and_skip(handle)
        entries_size, entries = _read_entries(handle)

        for entry in entries:
            entry.data = _read_entry_data(handle, entry)

        return cls(
            path=path,
            entries=entries,
            form_size=form_size,
            data_size=data_size,
            entries_size=entries_size,
        )

    def extract_all(self, destination: Union[str, Path], include_archive_folder: bool = True) -> int:
        root = Path(destination)
        if include_archive_folder:
            root = root / self.path.stem
        return self.extract_entries(self.entries, root)

    def extract_entries(
        self,
        entries: Iterable[PakEntry],
        destination: Union[str, Path],
        strip_prefix: Sequence[str] = (),
    ) -> int:
        root = Path(destination)
        count = 0
        for entry in entries:
            target = output_path_for_entry(root, entry.name, strip_prefix=strip_prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(entry.data)
            count += 1
        return count


def split_entry_name(name: str) -> Tuple[str, ...]:
    path = PureWindowsPath(name.replace("/", "\\"))
    if path.drive or path.is_absolute():
        raise PakFormatError("Archive entry uses an absolute path: %s" % name)

    parts = tuple(part for part in path.parts if part not in ("", ".", "\\", "/"))
    if not parts:
        raise PakFormatError("Archive entry has an empty path")
    if any(part == ".." for part in parts):
        raise PakFormatError("Archive entry tries to leave the output folder: %s" % name)
    return parts


def output_path_for_entry(
    destination: Union[str, Path],
    entry_name: str,
    strip_prefix: Sequence[str] = (),
) -> Path:
    parts = split_entry_name(entry_name)
    prefix = tuple(strip_prefix)
    if prefix:
        if parts[: len(prefix)] != prefix:
            raise PakFormatError("Entry %s is not inside selected prefix" % entry_name)
        parts = parts[len(prefix) :]
        if not parts:
            raise PakFormatError("Cannot extract a directory marker as a file")

    root = Path(destination)
    target = root.joinpath(*parts)

    root_resolved = root.resolve(strict=False)
    target_resolved = target.resolve(strict=False)
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PakFormatError("Archive entry escapes the output folder: %s" % entry_name) from exc

    return target


def _read_form(handle: BinaryIO) -> int:
    _expect_signature(handle, b"FORM")
    form_size = _read_int32_be(handle)
    _expect_signature(handle, b"PAC1")
    return form_size


def _read_head(handle: BinaryIO) -> None:
    _expect_signature(handle, b"HEAD")
    _skip(handle, 32)


def _read_data_header_and_skip(handle: BinaryIO) -> int:
    _expect_signature(handle, b"DATA")
    data_size = _read_int32_be(handle)
    _skip(handle, data_size)
    return data_size


def _read_entries(handle: BinaryIO) -> Tuple[int, List[PakEntry]]:
    _expect_signature(handle, b"FILE")
    entries_size = _read_int32_be(handle)
    size_field_end = handle.tell()
    _skip(handle, 2)
    _skip(handle, 4)
    entries_start = handle.tell()
    entries_end = _entry_table_end(handle, size_field_end, entries_start, entries_size)

    entries: List[PakEntry] = []

    while handle.tell() < entries_end:
        remaining = entries_end - handle.tell()
        if remaining < 2:
            break

        entry_type = _read_uint8(handle)
        name = _read_name(handle)
        if entry_type == ENTRY_DIRECTORY:
            _read_directory_entries(handle, name, entries)
        elif entry_type == ENTRY_FILE:
            entries.append(_read_file_entry(handle, name))
        else:
            raise PakFormatError("Unknown entry type %d at byte %d" % (entry_type, handle.tell() - 1))

    return entries_size, entries


def _entry_table_end(handle: BinaryIO, size_field_end: int, entries_start: int, entries_size: int) -> int:
    stream_end = _stream_length(handle)
    includes_prefix_end = size_field_end + entries_size
    excludes_prefix_end = entries_start + entries_size

    if includes_prefix_end == stream_end or excludes_prefix_end > stream_end:
        return min(includes_prefix_end, stream_end)
    return min(excludes_prefix_end, stream_end)


def _read_directory_entries(handle: BinaryIO, directory_name: str, entries: List[PakEntry]) -> None:
    child_count = _read_int32_le(handle)
    for _ in range(child_count):
        entry_type = _read_uint8(handle)
        child_name = "%s\\%s" % (directory_name, _read_name(handle))

        if entry_type == ENTRY_DIRECTORY:
            _read_directory_entries(handle, child_name, entries)
        elif entry_type == ENTRY_FILE:
            entries.append(_read_file_entry(handle, child_name))
        else:
            raise PakFormatError("Unknown child entry type %d at byte %d" % (entry_type, handle.tell() - 1))


def _read_file_entry(handle: BinaryIO, name: str) -> PakEntry:
    binary_offset = _read_int32_le(handle)
    size = _read_int32_le(handle)
    original_size = _read_int32_le(handle)
    _skip(handle, 4)
    compression_type = _read_int32_be(handle)
    unknown_data = _read_exact(handle, 4)

    return PakEntry(
        name=name,
        binary_offset=binary_offset,
        size=size,
        original_size=original_size,
        compression_type=compression_type,
        unknown_data=unknown_data,
    )


def _read_entry_data(handle: BinaryIO, entry: PakEntry) -> bytes:
    handle.seek(entry.binary_offset, io.SEEK_SET)
    payload = _read_exact(handle, entry.size)

    if entry.compression_type == COMPRESSION_ZLIB:
        return _decompress_payload(payload)

    return payload


def _decompress_payload(payload: bytes) -> bytes:
    attempts = (
        lambda: zlib.decompress(payload[2:], -zlib.MAX_WBITS),
        lambda: zlib.decompress(payload),
    )
    for attempt in attempts:
        try:
            return attempt()
        except zlib.error:
            continue
    return payload


def _read_name(handle: BinaryIO) -> str:
    name_length = _read_uint8(handle)
    return _read_exact(handle, name_length).decode("utf-8", errors="replace")


def _expect_signature(handle: BinaryIO, expected: bytes) -> None:
    offset = handle.tell()
    actual = _read_exact(handle, len(expected))
    if actual != expected:
        raise PakFormatError(
            "Expected %s at byte %d, found %r" % (expected.decode("ascii"), offset, actual)
        )


def _read_exact(handle: BinaryIO, size: int) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise PakFormatError("Unexpected end of file while reading %d bytes" % size)
    return data


def _skip(handle: BinaryIO, amount: int) -> None:
    if amount < 0:
        raise PakFormatError("Negative skip amount %d" % amount)
    handle.seek(amount, io.SEEK_CUR)


def _stream_length(handle: BinaryIO) -> int:
    position = handle.tell()
    handle.seek(0, io.SEEK_END)
    length = handle.tell()
    handle.seek(position, io.SEEK_SET)
    return length


def _read_uint8(handle: BinaryIO) -> int:
    return struct.unpack("<B", _read_exact(handle, 1))[0]


def _read_int32_le(handle: BinaryIO) -> int:
    return struct.unpack("<i", _read_exact(handle, 4))[0]


def _read_int32_be(handle: BinaryIO) -> int:
    return struct.unpack(">i", _read_exact(handle, 4))[0]
