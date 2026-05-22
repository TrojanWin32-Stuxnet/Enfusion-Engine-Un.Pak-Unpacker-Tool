from __future__ import annotations

import argparse
from typing import Optional, Sequence

from pakexplorer.pak import PakArchive

from .app import PakExplorerApp


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Explore and extract PAC1 PAK archives.")
    parser.add_argument("pak", nargs="*", help="PAK files to open")
    parser.add_argument("--extract", metavar="DIR", help="extract the given PAK files without opening the GUI")
    args = parser.parse_args(argv)

    if args.extract:
        if not args.pak:
            parser.error("--extract requires at least one PAK file")

        total = 0
        for pak_path in args.pak:
            archive = PakArchive.open(pak_path)
            total += archive.extract_all(args.extract, include_archive_folder=True)
        print("Extracted %d file%s." % (total, "" if total == 1 else "s"))
        return 0

    app = PakExplorerApp(args.pak)
    app.mainloop()
    return 0
