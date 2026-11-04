"""Pop-up for the flow export report: filter by type, search by name, and pick one or more flows."""

import tkinter as tk
from tkinter import messagebox, ttk

PAD = 8
ALL_TYPES = "All flow types"


def flow_label(flow: dict) -> str:
    return f"{flow.get('name') or flow['id']}   ({flow.get('type') or '?'})"


class FlowPickerDialog(tk.Toplevel):
    """Returns the chosen flow dicts in `self.result`, or None when cancelled."""

    def __init__(self, parent: tk.Tk, flows: list[dict]):
        super().__init__(parent)
        self.title("Export flows: choose flows")
        self.transient(parent)
        self.minsize(520, 420)
        self.result: list[dict] | None = None
        self.flows = flows
        self.selected: set[str] = set()
        self.shown: list[dict] = []

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ttk.Label(filters, text="Flow type").grid(row=0, column=0, sticky="w")
        self.type_var = tk.StringVar(value=ALL_TYPES)
        types = sorted({f.get("type") or "?" for f in flows})
        type_box = ttk.Combobox(filters, textvariable=self.type_var, values=[ALL_TYPES, *types], state="readonly", width=28)
        type_box.grid(row=0, column=1, sticky="w", padx=PAD)
        type_box.bind("<<ComboboxSelected>>", lambda _: self._render())
        ttk.Label(filters, text="Search").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._render())
        search = ttk.Entry(filters, textvariable=self.search_var, width=40)
        search.grid(row=1, column=1, sticky="w", padx=PAD, pady=(4, 0))

        listing = ttk.Frame(self)
        listing.pack(fill="both", expand=True, padx=PAD, pady=4)
        self.listbox = tk.Listbox(listing, selectmode="extended", activestyle="none", height=16, exportselection=False)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda _: self._sync_selection())

        tools = ttk.Frame(self)
        tools.pack(fill="x", padx=PAD)
        ttk.Button(tools, text="Select all shown", command=lambda: self._select_shown(True)).pack(side="left")
        ttk.Button(tools, text="Clear shown", command=lambda: self._select_shown(False)).pack(side="left", padx=4)
        self.count_label = ttk.Label(tools, foreground="#555")
        self.count_label.pack(side="right")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="▶  Export selected", command=self._accept).pack(side="right", padx=4)

        self._render()
        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()
        search.focus_set()

    def _render(self) -> None:
        flow_type, text = self.type_var.get(), self.search_var.get().strip().lower()
        self.shown = [
            f for f in self.flows
            if flow_type in (ALL_TYPES, f.get("type") or "?") and text in (f.get("name") or "").lower()
        ]
        self.listbox.delete(0, "end")
        for index, flow in enumerate(self.shown):
            self.listbox.insert("end", flow_label(flow))
            if flow["id"] in self.selected:
                self.listbox.selection_set(index)
        self._update_count()

    def _sync_selection(self) -> None:
        picked = set(self.listbox.curselection())
        for index, flow in enumerate(self.shown):
            (self.selected.add if index in picked else self.selected.discard)(flow["id"])
        self._update_count()

    def _select_shown(self, select: bool) -> None:
        for flow in self.shown:
            (self.selected.add if select else self.selected.discard)(flow["id"])
        self._render()

    def _update_count(self) -> None:
        self.count_label.config(text=f"{len(self.selected)} selected  ·  {len(self.shown)} of {len(self.flows)} shown")

    def _accept(self) -> None:
        chosen = [f for f in self.flows if f["id"] in self.selected]
        if not chosen:
            messagebox.showwarning("Choose flows", "Please select at least one flow to export.", parent=self)
            return
        self.result = chosen
        self.destroy()
