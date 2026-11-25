"""Safety Center: opt-in periodic monitoring while the desktop app is running."""
from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from .safety import SafetyIndex, duplicates


class SafetyCenter:
    def __init__(self, app, tabs, self_test=False):
        self.app, self.tabs = app, tabs
        self.active_root = None
        self.busy = False
        self.due = None
        self.events = queue.Queue()
        self.display_root = None
        self.frame = ttk.Frame(tabs, padding=12)
        tabs.insert(0, self.frame, text='Safety Center')
        tabs.select(self.frame)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)
        ttk.Label(self.frame, text='Monitor a project folder', font=('TkDefaultFont', 13, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(self.frame, text='Watch changes every 60 seconds while BreakCheck is open. Alerts are after-the-fact, not deletion protection.', wraplength=850).grid(row=1, column=0, sticky='w', pady=4)
        controls = ttk.Frame(self.frame)
        controls.grid(row=2, column=0, sticky='ew', pady=6)
        self.buttons = {}
        for key, title, callback in [('start','Start monitoring',self.start),('stop','Stop',self.stop),('check','Check now',self.check),('dupes','Find duplicates',self.find)]:
            button = ttk.Button(controls, text=title, command=callback)
            button.pack(side='left', padx=(0, 6))
            self.buttons[key] = button
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

    def start(self):
        root = self.folder()
        if root is not None:
            self.active_root = root
            self.run(root, 'snapshot')

    def stop(self):
        self.active_root = None
        if self.due is not None:
            self.app.after_cancel(self.due)
            self.due = None
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
        if self.due is not None:
            self.app.after_cancel(self.due)
            self.due = None
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
            elif kind == 'duplicates':
                self.render_duplicates(root, value)
            else:
                self.status.set(f'{root}: check failed — {value}')
            if self.active_root is not None:
                self.due = self.app.after(60000, self.tick)
        self.app.after(150, self.poll)

    def tick(self):
        self.due = None
        if self.active_root is not None:
            self.run(self.active_root, 'snapshot')

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
        mode = 'Monitoring' if self.active_root is not None else 'Snapshot'
        self.status.set(f'{mode}: {root} | {result.files:,} files | {result.bytes / 1048576:,.1f} MiB | {len(result.alerts)} previously known broken links | {len(result.warnings)} scan warnings')

    def render_duplicates(self, root, result):
        groups, skipped = result
        self.panes.select(self.dupes.master)
        self.fill(self.dupes, [(i, p, f'{size:,}') for i,(size,paths) in enumerate(groups,1) for p in paths][:2000])
        extra = sum(size*(len(paths)-1) for size,paths in groups)
        self.status.set(f'{root}: {len(groups)} duplicate groups | {extra / 1048576:,.1f} MiB additional copies (logical size) | {skipped} candidates skipped. Review dependencies before removing anything.')
