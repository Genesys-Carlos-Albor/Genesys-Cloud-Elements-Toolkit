"""Pop-up for the audit log report: service / entity type / action pickers and a two-calendar date range."""

import calendar
import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

from .reports.audit_logs import MAX_DAYS_PER_QUERY, AuditQuery, earliest_start

PAD = 8
ALL_ENTITIES = "All entity types"
ALL_ACTIONS = "All actions"
SELECTED_BG, RANGE_BG, NORMAL_BG = "#1f6feb", "#dbe9ff", "#ffffff"


class CalendarPicker(ttk.Frame):
    """Month grid with previous/next buttons; days outside min..max can't be picked."""

    def __init__(self, parent, selected: date, min_date: date, max_date: date, on_select):
        super().__init__(parent)
        self.selected, self.min_date, self.max_date, self.on_select = selected, min_date, max_date, on_select
        self.shown = selected.replace(day=1)
        self.range: tuple[date, date] = (selected, selected)
        self.weeks = calendar.Calendar(firstweekday=calendar.SUNDAY)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 4))
        self.prev_button = ttk.Button(header, text="◀", width=3, command=lambda: self._move(-1))
        self.prev_button.pack(side="left")
        self.month_label = ttk.Label(header, anchor="center", font=("Segoe UI", 10, "bold"))
        self.month_label.pack(side="left", expand=True, fill="x")
        self.next_button = ttk.Button(header, text="▶", width=3, command=lambda: self._move(1))
        self.next_button.pack(side="right")

        for col, name in enumerate(["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]):
            ttk.Label(self, text=name, anchor="center", foreground="#555").grid(row=1, column=col, sticky="ew")
        self.buttons = []
        for row in range(6):
            for col in range(7):
                button = tk.Button(self, width=3, relief="flat", bd=0, padx=2, pady=2, cursor="hand2")
                button.grid(row=row + 2, column=col, padx=1, pady=1)
                self.buttons.append(button)
        self.render()

    def _move(self, months: int) -> None:
        month_index = self.shown.year * 12 + self.shown.month - 1 + months
        self.shown = date(month_index // 12, month_index % 12 + 1, 1)
        self.render()

    def show(self, day: date) -> None:
        self.shown = day.replace(day=1)
        self.render()

    def set(self, day: date, start: date, end: date) -> None:
        self.selected, self.range = day, (start, end)
        if (day.year, day.month) != (self.shown.year, self.shown.month):
            self.shown = day.replace(day=1)
        self.render()

    def render(self) -> None:
        self.month_label.config(text=f"{calendar.month_name[self.shown.month]} {self.shown.year}")
        self.prev_button.config(state="normal" if self.shown > self.min_date.replace(day=1) else "disabled")
        self.next_button.config(state="normal" if self.shown < self.max_date.replace(day=1) else "disabled")
        days = [d for week in self.weeks.monthdatescalendar(self.shown.year, self.shown.month) for d in week]
        days += [days[-1] + timedelta(days=i) for i in range(1, 43 - len(days))]
        today = date.today()
        for button, day in zip(self.buttons, days):
            enabled = self.min_date <= day <= self.max_date
            in_month = day.month == self.shown.month
            if day == self.selected:
                bg, fg = SELECTED_BG, "#ffffff"
            elif self.range[0] <= day <= self.range[1] and in_month:
                bg, fg = RANGE_BG, "#000000"
            else:
                bg, fg = NORMAL_BG, "#000000" if in_month else "#999999"
            button.config(
                text=str(day.day), bg=bg, fg=fg, activebackground=RANGE_BG,
                state="normal" if enabled else "disabled", disabledforeground="#cccccc",
                font=("Segoe UI", 9, "bold" if day == today else "normal"),
                command=lambda d=day: self.on_select(d),
            )


class AuditQueryDialog(tk.Toplevel):
    """Returns an AuditQuery in `self.result`, or None when cancelled."""

    def __init__(self, parent: tk.Tk, services: list[dict]):
        super().__init__(parent)
        self.title("Audit logs: choose scope and dates")
        self.resizable(False, False)
        self.transient(parent)
        self.result: AuditQuery | None = None
        self.services = {s["name"]: s for s in services}
        self.today = date.today()
        self.min_date = earliest_start(self.today)
        self.start, self.end = self.today - timedelta(days=6), self.today

        self._build_scope()
        self._build_dates()
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=PAD, pady=PAD)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="▶  Run report", command=self._accept).pack(side="right", padx=4)

        self._service_changed()
        self._refresh_dates()
        self.bind("<Escape>", lambda _: self.destroy())
        self.grab_set()
        self.focus_set()

    # ---------- scope ----------

    def _build_scope(self) -> None:
        frame = ttk.LabelFrame(self, text="Scope")
        frame.pack(fill="x", padx=PAD, pady=(PAD, 0))
        self.service_var, self.entity_var, self.action_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        names = list(self.services)
        self.service_var.set(names[0] if names else "")
        rows = [
            ("Service", self.service_var, names, self._service_changed),
            ("Entity type", self.entity_var, [], self._entity_changed),
            ("Action", self.action_var, [], None),
        ]
        self.boxes = {}
        for row, (label, var, values, handler) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=4)
            box = ttk.Combobox(frame, textvariable=var, values=values, state="readonly", width=48, height=20)
            box.grid(row=row, column=1, sticky="w", padx=PAD, pady=4)
            if handler:
                box.bind("<<ComboboxSelected>>", lambda _, h=handler: h())
            self.boxes[label] = box

    def _service_changed(self) -> None:
        service = self.services.get(self.service_var.get(), {"entities": []})
        self.boxes["Entity type"]["values"] = [ALL_ENTITIES] + [e["name"] for e in service["entities"]]
        self.entity_var.set(ALL_ENTITIES)
        self._entity_changed()

    def _entity_changed(self) -> None:
        service = self.services.get(self.service_var.get(), {"entities": []})
        entity = self.entity_var.get()
        actions = sorted({a for e in service["entities"] if entity in (ALL_ENTITIES, e["name"]) for a in e.get("actions") or []})
        self.boxes["Action"]["values"] = [ALL_ACTIONS] + actions
        self.action_var.set(ALL_ACTIONS)

    # ---------- dates ----------

    def _build_dates(self) -> None:
        frame = ttk.LabelFrame(self, text="Date range")
        frame.pack(fill="x", padx=PAD, pady=PAD)
        presets = ttk.Frame(frame)
        presets.pack(fill="x", padx=PAD, pady=(PAD, 4))
        ttk.Label(presets, text="Quick pick:").pack(side="left")
        for label, days in [("Today", 1), ("Last 7 days", 7), ("Last 30 days", 30), ("Last 90 days", 90), ("Last 365 days", 365)]:
            ttk.Button(presets, text=label, command=lambda d=days: self._preset(d)).pack(side="left", padx=2)

        calendars = ttk.Frame(frame)
        calendars.pack(padx=PAD, pady=4)
        from_frame = ttk.LabelFrame(calendars, text="From")
        from_frame.pack(side="left", padx=(0, PAD))
        to_frame = ttk.LabelFrame(calendars, text="To")
        to_frame.pack(side="left")
        self.from_cal = CalendarPicker(from_frame, self.start, self.min_date, self.today, self._pick_start)
        self.from_cal.pack(padx=4, pady=4)
        self.to_cal = CalendarPicker(to_frame, self.end, self.min_date, self.today, self._pick_end)
        self.to_cal.pack(padx=4, pady=4)

        self.summary = ttk.Label(frame, font=("Segoe UI", 10, "bold"))
        self.summary.pack(anchor="w", padx=PAD)
        ttk.Label(
            frame, foreground="#555",
            text=f"Days are in your local time. Audit history goes back 365 days (to {self.min_date:%b %d, %Y}). "
                 f"Ranges over {MAX_DAYS_PER_QUERY} days run as several queries.",
            wraplength=560, justify="left",
        ).pack(anchor="w", padx=PAD, pady=(2, PAD))

    def _preset(self, days: int) -> None:
        self.start, self.end = max(self.today - timedelta(days=days - 1), self.min_date), self.today
        self._refresh_dates(show=True)

    def _pick_start(self, day: date) -> None:
        self.start = day
        self.end = max(self.end, day)
        self._refresh_dates()

    def _pick_end(self, day: date) -> None:
        self.end = day
        self.start = min(self.start, day)
        self._refresh_dates()

    def _refresh_dates(self, show: bool = False) -> None:
        self.from_cal.set(self.start, self.start, self.end)
        self.to_cal.set(self.end, self.start, self.end)
        if show:
            self.from_cal.show(self.start)
            self.to_cal.show(self.end)
        days = (self.end - self.start).days + 1
        queries = -(-days // MAX_DAYS_PER_QUERY)
        self.summary.config(
            text=f"{self.start:%a %b %d, %Y}  to  {self.end:%a %b %d, %Y}   ·   {days} day{'s' * (days != 1)}"
                 f"   ·   {queries} quer{'ies' if queries != 1 else 'y'}"
        )

    # ---------- result ----------

    def _accept(self) -> None:
        if not self.service_var.get():
            messagebox.showwarning("Choose a service", "Please choose an audit service.", parent=self)
            return
        entity, action = self.entity_var.get(), self.action_var.get()
        self.result = AuditQuery(
            service=self.service_var.get(),
            entity_type=None if entity == ALL_ENTITIES else entity,
            action=None if action == ALL_ACTIONS else action,
            start=self.start,
            end=self.end,
        )
        self.destroy()
