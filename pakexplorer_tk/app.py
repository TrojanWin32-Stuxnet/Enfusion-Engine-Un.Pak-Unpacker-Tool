from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pakexplorer.pak import PakArchive, PakEntry, PakFormatError, split_entry_name
from pakexplorer.preview import archive_summary, entry_preview, format_size


class PakExplorerApp(tk.Tk):
    def __init__(self, initial_paths: Optional[Iterable[str]] = None) -> None:
        super().__init__()
        self.title("PakExplorer TK")
        self.geometry("1120x720")
        self.minsize(760, 460)

        self.archives: Dict[str, PakArchive] = {}
        self.node_entries: Dict[str, Tuple[PakArchive, PakEntry]] = {}
        self.node_directories: Dict[str, Tuple[PakArchive, Tuple[str, ...]]] = {}

        self._build_menu()
        self._build_layout()

        if initial_paths:
            self.load_paths(initial_paths)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open PAK...", accelerator="Ctrl+O", command=self.open_dialog)
        file_menu.add_command(label="Extract Selected...", command=self.extract_selected_dialog)
        file_menu.add_command(label="Extract All...", command=self.extract_all_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menu_bar)

        self.bind_all("<Control-o>", lambda _event: self.open_dialog())

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(toolbar, text="Open PAK", command=self.open_dialog).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Extract Selected", command=self.extract_selected_dialog).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Extract All", command=self.extract_all_dialog).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.status_var = tk.StringVar(value="Open a .pak file to begin.")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.RIGHT)

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        tree_frame = ttk.Frame(paned)
        preview_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=1)
        paned.add(preview_frame, weight=2)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("size", "compression"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("compression", text="Compression")
        self.tree.column("#0", width=360, minwidth=180)
        self.tree.column("size", width=100, anchor=tk.E, stretch=False)
        self.tree.column("compression", width=120, anchor=tk.W, stretch=False)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.preview = tk.Text(preview_frame, wrap=tk.NONE, undo=False)
        self.preview.configure(font=("Consolas", 10), state=tk.DISABLED)
        y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview.yview)
        x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview.xview)
        self.preview.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.preview.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self._set_preview("Open a .pak file, then select an entry to preview it.")

    def open_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Open PAK archive",
            filetypes=(("PAK files", "*.pak"), ("All files", "*.*")),
        )
        if paths:
            self.load_paths(paths)

    def load_paths(self, paths: Iterable[str]) -> None:
        loaded = 0
        for raw_path in paths:
            try:
                archive = PakArchive.open(raw_path)
            except (OSError, PakFormatError) as exc:
                messagebox.showerror("Could not open PAK", "%s\n\n%s" % (raw_path, exc), parent=self)
                continue

            self._add_archive(archive)
            loaded += 1

        if loaded:
            self.status_var.set("Loaded %d archive%s." % (loaded, "" if loaded == 1 else "s"))

    def _add_archive(self, archive: PakArchive) -> None:
        archive_id = self.tree.insert(
            "",
            tk.END,
            text=archive.path.name,
            values=("%d files" % len(archive.entries), "archive"),
            open=True,
        )
        self.archives[archive_id] = archive

        directory_nodes: Dict[Tuple[str, ...], str] = {(): archive_id}

        for entry in sorted(archive.entries, key=lambda item: item.name.lower()):
            parts = split_entry_name(entry.name)
            parent_id = archive_id
            prefix: List[str] = []

            for part in parts[:-1]:
                prefix.append(part)
                key = tuple(prefix)
                if key not in directory_nodes:
                    directory_nodes[key] = self.tree.insert(
                        parent_id,
                        tk.END,
                        text=part,
                        values=("", "folder"),
                        open=False,
                    )
                    self.node_directories[directory_nodes[key]] = (archive, key)
                parent_id = directory_nodes[key]

            file_id = self.tree.insert(
                parent_id,
                tk.END,
                text=parts[-1],
                values=(format_size(entry.display_size), entry.compression_label),
                tags=("file",),
            )
            self.node_entries[file_id] = (archive, entry)

    def _selection_changed(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        node_id = selected[0]
        if node_id in self.node_entries:
            _archive, entry = self.node_entries[node_id]
            self._set_preview(entry_preview(entry))
            self.status_var.set("%s, %s" % (entry.name, format_size(entry.display_size)))
            return

        if node_id in self.node_directories:
            archive, prefix = self.node_directories[node_id]
            entries = _entries_under_prefix(archive, prefix)
            self._set_preview(
                "%s\n\n%d file%s in this folder."
                % ("\\".join(prefix), len(entries), "" if len(entries) == 1 else "s")
            )
            self.status_var.set("%d file%s selected by folder." % (len(entries), "" if len(entries) == 1 else "s"))
            return

        if node_id in self.archives:
            archive = self.archives[node_id]
            self._set_preview(archive_summary(archive))
            self.status_var.set("%s loaded." % archive.path.name)

    def extract_all_dialog(self) -> None:
        if not self.archives:
            messagebox.showinfo("Nothing to extract", "Open a PAK archive first.", parent=self)
            return

        destination = filedialog.askdirectory(parent=self, title="Extract all archives to...")
        if not destination:
            return

        total = 0
        try:
            for archive in self.archives.values():
                total += archive.extract_all(destination, include_archive_folder=True)
        except (OSError, PakFormatError) as exc:
            messagebox.showerror("Extract failed", str(exc), parent=self)
            return

        self.status_var.set("Extracted %d file%s." % (total, "" if total == 1 else "s"))
        messagebox.showinfo("Extract complete", "Extracted %d file%s." % (total, "" if total == 1 else "s"), parent=self)

    def extract_selected_dialog(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Nothing selected", "Select a file, folder, or archive first.", parent=self)
            return

        node_id = selected[0]
        if node_id in self.node_entries:
            self._extract_selected_file(node_id)
            return

        if node_id in self.node_directories:
            self._extract_selected_directory(node_id)
            return

        if node_id in self.archives:
            self._extract_selected_archive(node_id)
            return

    def _extract_selected_file(self, node_id: str) -> None:
        _archive, entry = self.node_entries[node_id]
        parts = split_entry_name(entry.name)
        target = filedialog.asksaveasfilename(parent=self, title="Extract file as...", initialfile=parts[-1])
        if not target:
            return

        try:
            Path(target).write_bytes(entry.data)
        except OSError as exc:
            messagebox.showerror("Extract failed", str(exc), parent=self)
            return

        self.status_var.set("Extracted %s." % entry.name)

    def _extract_selected_directory(self, node_id: str) -> None:
        archive, prefix = self.node_directories[node_id]
        destination = filedialog.askdirectory(parent=self, title="Extract selected folder to...")
        if not destination:
            return

        entries = _entries_under_prefix(archive, prefix)
        try:
            count = archive.extract_entries(entries, destination, strip_prefix=prefix)
        except (OSError, PakFormatError) as exc:
            messagebox.showerror("Extract failed", str(exc), parent=self)
            return

        self.status_var.set("Extracted %d file%s." % (count, "" if count == 1 else "s"))

    def _extract_selected_archive(self, node_id: str) -> None:
        archive = self.archives[node_id]
        destination = filedialog.askdirectory(parent=self, title="Extract selected archive to...")
        if not destination:
            return

        try:
            count = archive.extract_all(destination, include_archive_folder=True)
        except (OSError, PakFormatError) as exc:
            messagebox.showerror("Extract failed", str(exc), parent=self)
            return

        self.status_var.set("Extracted %d file%s." % (count, "" if count == 1 else "s"))

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)


def _entries_under_prefix(archive: PakArchive, prefix: Sequence[str]) -> List[PakEntry]:
    prefix_tuple = tuple(prefix)
    return [
        entry
        for entry in archive.entries
        if split_entry_name(entry.name)[: len(prefix_tuple)] == prefix_tuple
    ]


def main(argv: Optional[Sequence[str]] = None) -> int:
    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
