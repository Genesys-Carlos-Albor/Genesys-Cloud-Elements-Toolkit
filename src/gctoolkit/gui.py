"""Desktop app: pick an org and a report, run it, and open the result."""

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import __version__, export, profiles, settings, updates, use_system_certificates
from .client import GenesysClient
from .reports import Report, load_all
from .runner import run_report

PAD = 8


class AddProfileDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Add org profile")
        self.resizable(False, False)
        self.transient(parent)
        self.result: profiles.Profile | None = None

        self.vars = {key: tk.StringVar() for key in ("name", "environment", "client_id", "secret")}
        self.vars["environment"].set("mypurecloud.com")
        fields = [
            ("Profile name", ttk.Entry(self, textvariable=self.vars["name"], width=40)),
            ("Region", ttk.Combobox(self, textvariable=self.vars["environment"], values=list(settings.REGIONS), width=38)),
            ("Client ID", ttk.Entry(self, textvariable=self.vars["client_id"], width=40)),
            ("Client secret", ttk.Entry(self, textvariable=self.vars["secret"], width=40, show="•")),
        ]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=PAD, pady=4)
            widget.grid(row=row, column=1, padx=PAD, pady=4)
        buttons = ttk.Frame(self)
        buttons.grid(row=len(fields), column=0, columnspan=2, pady=PAD)
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        fields[0][1].focus_set()
        self.grab_set()

    def _save(self) -> None:
        values = {k: v.get().strip() for k, v in self.vars.items()}
        if not all(values.values()):
            messagebox.showwarning("Missing details", "Please fill in every field.", parent=self)
            return
        self.result = profiles.add_profile(values["name"], values["environment"], values["client_id"], values["secret"])
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Genesys Cloud Elements Toolkit {__version__}")
        self.geometry("1000x680")
        self.minsize(820, 560)

        self.reports = load_all()
        self.config_data = settings.load()
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
        self.last_file: Path | None = None

        self._build_org_bar()
        self._build_main()
        self._build_settings_bar()
        self._refresh_profiles()
        self.after(100, self._poll_messages)
        if self.config_data.get("check_for_updates", True):
            self.after(1500, lambda: self._check_updates(manual=False))

    # ---------- layout ----------

    def _build_org_bar(self) -> None:
        bar = ttk.LabelFrame(self, text="Org")
        bar.pack(fill="x", padx=PAD, pady=(PAD, 0))
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(bar, textvariable=self.profile_var, state="readonly", width=45)
        self.profile_box.pack(side="left", padx=PAD, pady=PAD)
        self.profile_box.bind("<<ComboboxSelected>>", lambda _: self._remember_profile())
        ttk.Button(bar, text="Test login", command=self._test_login).pack(side="left", padx=2)
        ttk.Button(bar, text="Add…", command=self._add_profile).pack(side="left", padx=2)
        ttk.Button(bar, text="Import from gc CLI", command=self._import_profiles).pack(side="left", padx=2)
        ttk.Button(bar, text="Remove", command=self._remove_profile).pack(side="left", padx=2)

    def _build_main(self) -> None:
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        left = ttk.LabelFrame(panes, text="Reports")
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._show_report())
        self.tree.bind("<Double-1>", lambda _: self._run_selected())
        by_category: dict[str, list[Report]] = {}
        for report in self.reports.values():
            by_category.setdefault(report.category, []).append(report)
        for category in sorted(by_category):
            parent = self.tree.insert("", "end", text=category, open=True)
            for report in sorted(by_category[category], key=lambda r: r.title):
                self.tree.insert(parent, "end", iid=report.key, text=report.title)
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        details = ttk.LabelFrame(right, text="Details")
        details.pack(fill="x")
        self.title_label = ttk.Label(details, text="Select a report", font=("Segoe UI", 12, "bold"))
        self.title_label.pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.desc_label = ttk.Label(details, text="", wraplength=560, justify="left")
        self.desc_label.pack(anchor="w", padx=PAD)
        self.meta_label = ttk.Label(details, text="", foreground="#555")
        self.meta_label.pack(anchor="w", padx=PAD, pady=(2, PAD))

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=PAD)
        self.run_button = ttk.Button(actions, text="▶  Run report", command=self._run_selected, state="disabled")
        self.run_button.pack(side="left")
        self.open_file_button = ttk.Button(actions, text="Open last report", command=self._open_last, state="disabled")
        self.open_file_button.pack(side="left", padx=4)
        self.open_folder_button = ttk.Button(actions, text="Show in folder", command=self._reveal_last, state="disabled")
        self.open_folder_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=160)
        self.progress.pack(side="right")

        log_frame = ttk.LabelFrame(right, text="Progress")
        log_frame.pack(fill="both", expand=True)
        self.log_box = ScrolledText(log_frame, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, padx=4, pady=4)
        panes.add(right, weight=3)

    def _build_settings_bar(self) -> None:
        bar = ttk.LabelFrame(self, text="Settings")
        bar.pack(fill="x", padx=PAD, pady=(0, PAD))
        ttk.Label(bar, text="Save reports to:").pack(side="left", padx=(PAD, 4), pady=PAD)
        self.save_var = tk.StringVar(value=self.config_data["save_location"])
        ttk.Entry(bar, textvariable=self.save_var, width=50, state="readonly").pack(side="left")
        ttk.Button(bar, text="Browse…", command=self._choose_save_location).pack(side="left", padx=4)
        self.open_after_var = tk.BooleanVar(value=self.config_data.get("open_after_export", True))
        ttk.Checkbutton(
            bar, text="Open Excel and the folder when a report finishes",
            variable=self.open_after_var, command=self._save_settings,
        ).pack(side="left", padx=PAD)
        ttk.Button(bar, text="Check for updates", command=lambda: self._check_updates(manual=True)).pack(
            side="right", padx=PAD,
        )

    # ---------- profiles ----------

    def _refresh_profiles(self, select: str | None = None) -> None:
        names = [p.name for p in profiles.list_profiles()]
        self.profile_box["values"] = names
        choice = select or self.config_data.get("last_profile")
        self.profile_var.set(choice if choice in names else (names[0] if names else ""))
        if not names:
            self._log("No org profiles yet. Use 'Import from gc CLI' or 'Add…' to create one.")

    def _selected_profile(self) -> profiles.Profile | None:
        name = self.profile_var.get()
        if not name:
            messagebox.showinfo("Choose an org", "Add or import an org profile first.")
            return None
        return profiles.get_profile(name)

    def _remember_profile(self) -> None:
        self.config_data["last_profile"] = self.profile_var.get()
        settings.save(self.config_data)

    def _add_profile(self) -> None:
        dialog = AddProfileDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            self._refresh_profiles(select=dialog.result.name)
            self._log(f"Saved profile '{dialog.result.name}'.")

    def _import_profiles(self) -> None:
        if not messagebox.askyesno(
            "Import profiles",
            "Copy every client-credentials profile from the Genesys Cloud CLI (~/.gc/config.toml) "
            "into this app? Secrets are stored in the OS credential store.",
        ):
            return
        try:
            imported, skipped = profiles.import_gc_cli_profiles()
        except profiles.ProfileError as err:
            messagebox.showerror("Import failed", str(err))
            return
        self._refresh_profiles()
        self._log(f"Imported {len(imported)} profile(s); skipped {len(skipped)} already present or unsupported.")

    def _remove_profile(self) -> None:
        name = self.profile_var.get()
        if name and messagebox.askyesno("Remove profile", f"Remove '{name}' and its stored secret?"):
            profiles.remove_profile(name)
            self._refresh_profiles()
            self._log(f"Removed profile '{name}'.")

    def _test_login(self) -> None:
        profile = self._selected_profile()
        if profile:
            self._start(f"Testing login for {profile.name}...", lambda log: self._login_check(profile, log))

    @staticmethod
    def _login_check(profile: profiles.Profile, log) -> None:
        org = GenesysClient(profile).get("/api/v2/organizations/me")
        log(f"OK: '{profile.name}' is connected to org '{org.get('name')}'.")

    # ---------- reports ----------

    def _selected_report(self) -> Report | None:
        selection = self.tree.selection()
        return self.reports.get(selection[0]) if selection else None

    def _show_report(self) -> None:
        report = self._selected_report()
        if not report:
            self.run_button.config(state="disabled")
            return
        self.title_label.config(text=report.title)
        self.desc_label.config(text=report.description)
        impact = "⚠ Changes data in the org" if report.modifies_org else "Read-only"
        self.meta_label.config(text=f"{impact}   •   Ported from: {report.source_script}")
        self.run_button.config(state="disabled" if self.busy else "normal")

    def _run_selected(self) -> None:
        report, profile = self._selected_report(), self._selected_profile()
        if not report or not profile or self.busy:
            return
        if report.modifies_org and not messagebox.askyesno(
            "Confirm changes", f"'{report.title}' will CHANGE data in org '{profile.name}'.\n\nContinue?", icon="warning",
        ):
            return
        self._start(
            f"\n=== {report.title} — {profile.name} ===",
            lambda log: run_report(report, profile, log, open_after=False),
            on_done=self._report_finished,
        )

    def _report_finished(self, path: Path | None) -> None:
        if not path:
            return
        self.last_file = path
        self.open_file_button.config(state="normal")
        self.open_folder_button.config(state="normal")
        if self.open_after_var.get():
            export.reveal_in_folder(path)
            export.open_file(path)

    def _open_last(self) -> None:
        if self.last_file and self.last_file.exists():
            export.open_file(self.last_file)

    def _reveal_last(self) -> None:
        if self.last_file and self.last_file.exists():
            export.reveal_in_folder(self.last_file)

    # ---------- settings ----------

    def _choose_save_location(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.save_var.get(), title="Choose where reports are saved")
        if folder:
            self.save_var.set(str(Path(folder)))
            self._save_settings()

    def _save_settings(self) -> None:
        self.config_data["save_location"] = self.save_var.get()
        self.config_data["open_after_export"] = self.open_after_var.get()
        settings.save(self.config_data)

    # ---------- updates ----------

    def _check_updates(self, manual: bool) -> None:
        threading.Thread(
            target=lambda: self.messages.put(("update", (manual, updates.latest_release()))), daemon=True,
        ).start()

    def _update_result(self, manual: bool, release: updates.Release | None) -> None:
        if release is None:
            if manual:
                messagebox.showinfo("Check for updates", "Couldn't reach GitHub to check for updates. Try again later.")
            return
        newer = updates.parse_version(release.version) > updates.parse_version(__version__)
        if not newer:
            if manual:
                messagebox.showinfo("Check for updates", f"You have the latest version ({__version__}).")
            return
        if not manual and release.version == self.config_data.get("skipped_version"):
            return
        self._log(f"Version {release.version} is available (you have {__version__}).")

        notes = f"\n\nWhat's new:\n{release.notes[:600]}" if release.notes else ""
        if updates.is_frozen_exe():
            prompt = f"Version {release.version} is available (you have {__version__}).{notes}\n\nDownload it now?"
            url = release.exe_url or release.page_url
        else:
            prompt = (
                f"Version {release.version} is available (you have {__version__}).{notes}\n\n"
                f"To update, run:\n{updates.PIP_UPGRADE}\n\nOpen the release page?"
            )
            url = release.page_url
        if messagebox.askyesno("Update available", prompt):
            webbrowser.open(url)
            if updates.is_frozen_exe():
                self._log("Downloading the new version. Close this app, then run the downloaded file in its place.")
        elif not manual:
            self.config_data["skipped_version"] = release.version
            settings.save(self.config_data)

    # ---------- background work ----------

    def _start(self, banner: str, work, on_done=None) -> None:
        self.busy = True
        self.run_button.config(state="disabled")
        self.progress.start(12)
        self._log(banner)

        def worker():
            log = lambda message: self.messages.put(("log", message))
            try:
                result = work(log)
                self.messages.put(("done", (on_done, result)))
            except Exception as err:  # surfaced to the operator instead of crashing the window
                self.messages.put(("error", str(err)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "update":
                    self._update_result(*payload)
                else:
                    self.busy = False
                    self.progress.stop()
                    self.progress["value"] = 0
                    self._show_report()
                    if kind == "error":
                        self._log(f"ERROR: {payload}")
                        messagebox.showerror("Something went wrong", payload)
                    else:
                        on_done, result = payload
                        if on_done:
                            on_done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)

    def _log(self, message: str) -> None:
        self.log_box.config(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")


def main() -> None:
    use_system_certificates()
    App().mainloop()


if __name__ == "__main__":
    main()
