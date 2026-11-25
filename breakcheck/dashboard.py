"""Safety Center: opt-in periodic monitoring while the desktop app is running."""
from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .safety import SafetyIndex, duplicates
from .agent import Preferences, read_preferences, save_preferences, validated_root, Wakeup
from .tray import startup_supported, startup_enabled, set_startup


class SafetyCenter:
    def __init__(self, app, tabs, self_test=False):
        self.app, self.tabs = app, tabs
        self.active_root = None
        self.busy = False
        self.wakeup = None
        self.last_scan = float('-inf')
        self.previous_alerts = set()
        self.prefs = Preferences()
        self.events = queue.Queue()
        self.display_root = None
        self.frame = ttk.Frame(tabs, padding=12)
        tabs.insert(0, self.frame, text='Safety Center')
        tabs.select(self.frame)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)
        ttk.Label(self.frame, text='Monitor a project folder', font=('TkDefaultFont', 13, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(self.frame, text='Monitor a saved folder using file events when available, with a 60-second fallback. Windows can keep running in the notification area. Alerts are after-the-fact.', wraplength=850).grid(row=1, column=0, sticky='w', pady=4)
        controls = ttk.Frame(self.frame)
        controls.grid(row=2, column=0, sticky='ew', pady=6)
        self.buttons = {}
        for key, title, callback in [('start','Start monitoring',self.start),('stop','Stop',self.stop),('check','Check now',self.check),('dupes','Find duplicates',self.find)]:
            button = ttk.Button(controls, text=title, command=callback)
            button.pack(side='left', padx=(0, 6))
            self.buttons[key] = button
        self.notifications = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Notifications', variable=self.notifications, command=self.update_notifications).pack(side='left', padx=6)
        self.autostart = tk.BooleanVar(value=False)
        if not self_test and startup_supported():
            try:
                self.autostart.set(startup_enabled())
            except OSError:
                pass
            ttk.Checkbutton(controls, text='Start with Windows', variable=self.autostart, command=self.update_startup).pack(side='left', padx=6)
        self.status = tk.StringVar(value='Choose a scan folder above, then start monitoring or check now.')
        ttk.Label(self.frame, textvariable=self.status, wraplength=850).grid(row=3, column=0, sticky='w', pady=5)
        panes = ttk.Notebook(self.frame)
        self.panes = panes
        panes.grid(row=4, column=0, sticky='nsew')
        self.alerts = self.table(panes, 'Broken links', ('Dependent file','Missing target','Possible new location'))
        self.history = self.table(panes, 'File activity', ('Time','Change','Path','Details'))
        self.dupes = self.table(panes, 'Duplicates', ('Group','File','Size'))
        self.controls()
        if not self_test:
            app.after(150, self.poll)

    def table(self, panes, title, columns):
        frame = ttk.Frame(panes)
        panes.add(frame, text=title)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=180 if col not in ('Path','File','Dependent file','Missing target','Details') else 320)
        tree.grid(row=0, column=0, sticky='nsew')
        y = ttk.Scrollbar(frame, command=tree.yview)
        y.grid(row=0, column=1, sticky='ns')
        x = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        x.grid(row=1, column=0, sticky='ew')
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        return tree

    def controls(self):
        for key, button in self.buttons.items():
            disabled = (key != 'stop' and self.busy) or (key == 'start' and self.active_root is not None) or (key == 'stop' and self.active_root is None)
            button.configure(state='disabled' if disabled else 'normal')

    def folder(self):
        if self.active_root is not None:
            return self.active_root
        path = self.app.root_path.get().strip() or filedialog.askdirectory(parent=self.app)
        if path:
            self.app.root_path.set(path)
            return Path(path).expanduser().absolute()
        return None

    def resume(self):
        try:
            self.prefs = read_preferences()
            self.notifications.set(self.prefs.notifications)
            if self.prefs.root:
                self.activate(validated_root(self.prefs.root))
        except (OSError, ValueError, RuntimeError) as exc:
            self.status.set(f'Unable to resume monitoring: {exc}')

    def update_notifications(self):
        try:
            save_preferences(Preferences(self.prefs.root, self.notifications.get()))
            self.prefs.notifications = self.notifications.get()
        except (OSError, ValueError) as exc:
            self.notifications.set(self.prefs.notifications)
            messagebox.showerror('Preferences', str(exc), parent=self.app)

    def update_startup(self):
        try:
            set_startup(self.autostart.get())
        except (OSError, RuntimeError) as exc:
            self.autostart.set(not self.autostart.get())
            messagebox.showerror('Windows startup', str(exc), parent=self.app)

    def activate(self, root):
        self.active_root = root
        self.previous_alerts = set()
        self.wakeup = Wakeup(root)
        self.last_scan = float('-inf')
        if not self.app.target.get():
            self.app.root_path.set(str(root))
        self.run(root, 'snapshot')

    def start(self):
        root = self.folder()
        if root is not None:
            try:
                root = validated_root(root)
                prefs = Preferences(str(root), self.notifications.get())
                save_preferences(prefs)
                self.prefs = prefs
                self.activate(root)
            except (OSError, ValueError, RuntimeError) as exc:
                self.status.set(f'Unable to start monitoring: {exc}')

    def shutdown(self):
        if self.wakeup is not None:
            self.wakeup.close()
            self.wakeup = None
        self.active_root = None

    def stop(self):
        try:
            prefs = Preferences('', self.notifications.get())
            save_preferences(prefs)
            self.prefs = prefs
        except (OSError, ValueError) as exc:
            self.status.set(f'Unable to save stop preference: {exc}')
            return
        self.shutdown()
        self.controls()
        self.status.set('Monitoring stopped. An in-progress check will finish.')

    def check(self):
        root = self.folder()
        if root is not None:
            self.run(root, 'snapshot')

    def find(self):
        root = self.folder()
        if root is not None:
            self.run(root, 'duplicates')

    def run(self, root, kind):
        if self.busy:
            return
        if kind == 'snapshot' and self.wakeup is not None:
            self.wakeup.dirty.clear()
        if root != self.display_root:
            for tree in (self.alerts, self.history, self.dupes):
                self.fill(tree, [])
            self.tabs.tab(self.frame, text='Safety Center')
            self.display_root = root
        self.busy = True
        self.controls()
        self.status.set(f'Checking {root}…')
        def worker():
            try:
                value = SafetyIndex().refresh(root) if kind == 'snapshot' else duplicates(root)
                self.events.put((root, kind, value))
            except Exception as exc:
                self.events.put((root, 'error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            root, kind, value = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.controls()
            if kind == 'snapshot':
                self.render_snapshot(root, value)
                self.last_scan = time.monotonic()
                if self.active_root == root:
                    alerts = set(value.alerts)
                    new = alerts - self.previous_alerts
                    self.previous_alerts = alerts
                    if self.notifications.get() and getattr(self.app, 'tray', None):
                        self.app.tray.notify(len(new))
            elif kind == 'duplicates':
                self.render_duplicates(root, value)
            else:
                self.status.set(f'{root}: check failed — {value}')
                self.last_scan = time.monotonic()
        if not self.busy and self.active_root is not None and self.wakeup is not None and self.wakeup.due(self.last_scan, time.monotonic()):
            self.run(self.active_root, 'snapshot')
        self.app.after(500, self.poll)

    @staticmethod
    def fill(tree, rows):
        for child in tree.get_children():
            tree.delete(child)
        for row in rows:
            tree.insert('', 'end', values=row)

    def render_snapshot(self, root, result):
        moves = {}
        for _, action, old, new in result.history:
            if action == 'Possible move':
                moves.setdefault(old, new)
        self.fill(self.alerts, [(source, target, moves.get(target, '')) for source, target in result.alerts[:1000]])
        self.fill(self.history, [(datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S'),a,p,d) for t,a,p,d in result.history])
        self.tabs.tab(self.frame, text=f'Safety Center ({len(result.alerts)} alerts)' if result.alerts else 'Safety Center')
        mode = f'Monitoring ({self.wakeup.backend})' if self.active_root is not None and self.wakeup else 'Snapshot'
        self.status.set(f'{mode}: {root} | {result.files:,} files | {result.bytes / 1048576:,.1f} MiB | {len(result.alerts)} previously known broken links | {len(result.warnings)} scan warnings')

    def render_duplicates(self, root, result):
        groups, skipped = result
        self.panes.select(self.dupes.master)
        self.fill(self.dupes, [(i, p, f'{size:,}') for i,(size,paths) in enumerate(groups,1) for p in paths][:2000])
        extra = sum(size*(len(paths)-1) for size,paths in groups)
        self.status.set(f'{root}: {len(groups)} duplicate groups | {extra / 1048576:,.1f} MiB additional copies (logical size) | {skipped} candidates skipped. Review dependencies before removing anything.')
