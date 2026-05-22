# PakExplorer TK

Python/Tkinter unpacker and inspector for Arma Reforger `PAC1` `.pak` archives.

This project is for opening Reforger addon containers such as `data.pak`,
reading the internal file table, previewing extracted payloads, and writing the
contained assets back out to a normal folder tree.

In other words, reverse engineer data.pak files

---
## Instructions of Use:
```sh
git clone PLACEHOLDER
cd ArmaPakBook
```

```powershell
python -m pakexplorer_tk --extract out path\to\data.pak
```
---
## Features And currently implemented functions 

- open one or more Reforger `.pak` files
- parse the `PAC1` archive structure
- reconstruct nested folders and files from the archive table
- decompress supported compressed entries
- preview likely text files
- hex preview binary files
- extract a selected file, folder, archive, or all loaded archives
- run as either a GUI tool or a CLI extraction command - GUI under Releases

## Work in progress, coming soon. 

- repacking or editing `.pak` files
- semantic decoding of Reforger world formats
- terrain analysis, coordinate conversion, or ballistics w/ weather
- model, texture, or material viewers - W.I.P
# Contributors

## Rules for contributions

Your code must fit within the project's readability scope and must be a substantial feature. Bug fixes are all welcome.

## Repository Layout

```text
run.py                     launcher used by PyInstaller
pyproject.toml             package metadata and console entry points
pakexplorer.spec           PyInstaller build spec
pakexplorer/
  __init__.py              reusable parser exports
  pak.py                   PAC1 parser and extraction logic
  preview.py               text detection, summaries, hex dump
pakexplorer_tk/
  __init__.py              GUI package exports
  __main__.py              python -m entry point
  cli.py                   CLI mode selection and argument parsing
  app.py                   Tkinter desktop UI
```
---
# Theory Of findings Developing this project;

Reforger addon content is commonly distributed inside archive files such as:

- `data.pak`

Those archives contain the actual project assets used by maps and addons, for
example:

- world definitions
- `.layer` files
- scripts
- configs
- models
- terrain-related assets

The purpose of this tool is to cross that archive boundary. After extraction,
the Reforger assets are available as normal files for inspection or use by
other tools. 
### Parser:
The parser entry point is `PakArchive.open(...)` in [pakexplorer/pak.py](pakexplorer/pak.py).

Current parser model:

1. read `FORM`
2. read big-endian form size
3. verify `PAC1`
4. read `HEAD`
5. skip 32 bytes of currently opaque header data
6. read `DATA`
7. read big-endian data size
8. skip the packed data block to reach the file table
9. read `FILE`
10. parse directory and file records
11. seek back to each stored payload offset
12. materialize file data in memory

Observed field layout used by the parser:

- top-level chunk signature: `FORM`
- format signature: `PAC1`
- `DATA` chunk size: big-endian `int32`
- `FILE` chunk size: big-endian `int32`
- entry type: one byte
- entry name length: one byte
- directory child count: little-endian `int32`
- file offset: little-endian `int32`
- packed size: little-endian `int32`
- original size: little-endian `int32`
- compression type: big-endian `int32`

Known compression values:

- `0`: uncompressed
- `0x106`: zlib/deflate

The implementation also handles a real-world Reforger variation in `FILE` chunk
accounting where the stored size may either:

- count only the file-table body
- count the 6-byte prefix before the first entry

That compatibility logic exists because real addon archives are not fully
consistent on this point.

## Extraction Model

Each parsed entry is represented by `PakEntry`, which includes:

- archived path
- payload offset
- packed size
- original size
- compression type
- extracted byte payload

Extraction helpers live in [pakexplorer/pak.py](pakexplorer/pak.py).

Path handling is intentionally strict:

- absolute archive paths are rejected
- `..` traversal is rejected
- destination paths are normalized before write

This matters because an unpacker should preserve Reforger's internal project
structure while refusing to let a malformed archive write outside the selected
output directory.

## Preview Model

Preview helpers live in [pakexplorer/preview.py](pakexplorer/preview.py).

Behavior:

- try `utf-8-sig`
- try `utf-16`
- reject obviously bad text based on embedded nulls and control-character ratio
- fall back to a fixed-size hex dump for binary payloads

This is useful for common Reforger content such as:

- scripts
- config-like files
- metadata
- plain-text world references

It is not a typed asset decoder. Binary Reforger formats still show as hex.



Launch the Tkinter explorer:

```powershell
python -m pakexplorer_tk
```

Open an archive immediately:

```powershell
python -m pakexplorer_tk path\to\data.pak
```

### CLI extraction mode

Extract one or more archives without opening the GUI:

```powershell
python -m pakexplorer_tk --extract out path\to\data.pak
```

### Installed command

Install from source:

```powershell
python -m pip install .
```

Then use either entry point:

```powershell
pakexplorer --extract out path\to\data.pak
pakexplorer-tk path\to\data.pak
```

The console script definitions are in [pyproject.toml](pyproject.toml).

## Building the Windows `.exe`

This repository already includes a PyInstaller spec file:

- [pakexplorer.spec](pakexplorer.spec)

Install PyInstaller in the active environment:

```powershell
python -m pip install pyinstaller
```

Build from the repository root:

```powershell
python -m PyInstaller pakexplorer.spec
```

Expected output:

- `dist\pakexplorer.exe`

Generated build directories:

- `build\`
- `dist\`

The spec builds from [run.py](run.py) and keeps `console=True`. That is the
correct setting for this project because the same executable supports both:

- GUI launch
- CLI extraction such as `pakexplorer.exe --extract out data.pak`

If you want to call the built executable from any terminal, either:

- place `dist\pakexplorer.exe` in a directory already on `Path`
- add the `dist` directory itself to `Path`

## How This Applies to Reforger Map Work

For Reforger map analysis, `data.pak` is the container, not the final input.
The useful output is the extracted content inside it.

For map-derived tooling such as a mortar calculator, the relevant files are
usually under:

- `Worlds\<MapName>\...`

The minimum useful input is usually not one arbitrary file. In practice, you
typically need:

- the main world definition for the map
- terrain height data referenced by that world
- world coordinate or transform metadata
- optionally `.layer` files for placed content

This tool's role in that workflow is:

1. open `data.pak`
2. extract the relevant world and terrain trees
3. inspect referenced files and asset relationships
4. hand those extracted files to the next analysis step

If the end goal is a mortar calculator, this unpacker does not solve terrain
math or ballistics. It solves the archive format so those files become
available to the code that does.

## Operational Limits

Current limits relevant to Reforger use:

- no repacking support
- no parser for higher-level Reforger world semantics
- no terrain sampling or map coordinate conversion
- no visual asset inspection beyond text/hex preview
- eager payload loading increases memory use on large addon packs

The eager-load approach is simple and keeps preview and extraction responsive
after open, but memory usage scales with the extracted payload size.

## Validation Status

The parser has been exercised against:

- synthetic PAC1 archives with nested directories and zlib entries
- real Arma Reforger addon archives, including `FILE` size variation

There is currently no comprehensive conformance suite in the repository.
