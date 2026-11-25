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
        self.frame = ttk.Frame(tabs)
        tabs.insert(0, self.frame, text='Overview')
        tabs.select(self.frame)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(5, weight=1)
        self.monitor_path = tk.StringVar()
        self.state = tk.StringVar(value='Not monitoring')
        heading = ttk.Frame(self.frame)
        heading.grid(row=0,column=0,sticky='ew')
        ttk.Label(heading,text='Safety overview',style='PageTitle.TLabel').pack(side='left')
        ttk.Label(heading,textvariable=self.state,style='Muted.TLabel').pack(side='right',pady=8)
        ttk.Label(self.frame, text='Monitor a project, inspect recent changes or find duplicate files.', style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(3,14))
        metrics = ttk.Frame(self.frame)
        metrics.grid(row=2,column=0,sticky='ew',pady=(0,14))
        self.metrics = {}
        for col, (key, name) in enumerate([('files','Files observed'),('size','Logical size'),('alerts','Broken links'),('changes','Recent changes')]):
            metrics.columnconfigure(col,weight=1,uniform='metrics')
            card = ttk.Frame(metrics,style='Card.TFrame',padding=(12,10))
            card.grid(row=0,column=col,sticky='nsew',padx=(0,8) if col<3 else 0)
            ttk.Label(card,text=name,style='CardCaption.TLabel').pack(anchor='w')
            value = tk.StringVar(value='—')
            ttk.Label(card,textvariable=value,style='Metric.TLabel').pack(anchor='w',pady=(4,0))
            self.metrics[key] = value
        controls = ttk.Frame(self.frame,style='Card.TFrame',padding=12)
        controls.grid(row=3,column=0,sticky='ew')
        controls.columnconfigure(0,weight=1)
        ttk.Label(controls,text='Folder to monitor or scan',style='Card.TLabel').grid(row=0,column=0,sticky='w',pady=(0,5))
        self.folder_entry = ttk.Entry(controls,textvariable=self.monitor_path)
        self.folder_entry.grid(row=1,column=0,sticky='ew',padx=(0,8))
        self.browse = ttk.Button(controls,text='Browse',command=self.browse_folder)
        self.browse.grid(row=1,column=1,sticky='ew')
        actions = ttk.Frame(controls,style='Card.TFrame')
        actions.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(10,0))
        self.buttons = {}
        for key,title,callback in [('start','Start monitoring',self.start),('stop','Stop',self.stop),('check','Check now',self.check),('dupes','Find duplicates',self.find)]:
            button = ttk.Button(actions,text=title,command=callback,style='Accent.TButton' if key=='start' else 'TButton')
            button.pack(side='left',padx=(0,6))
            self.buttons[key]=button
        self.status = tk.StringVar(value='Choose a project folder to begin. Whole-drive checks show a limited storage overview.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=720).grid(row=4,column=0,sticky='ew',pady=10)
        panes = ttk.Notebook(self.frame)
        self.panes = panes
        panes.grid(row=5,column=0,sticky='nsew')
        self.alerts = self.table(panes,'Broken links',('Dependent file','Missing target','Possible new location'))
        self.history = self.table(panes,'Activity',('Time','Change','Path','Details'))
        self.dupes = self.table(panes,'Duplicates',('Group','File','Size'))
        self.largest = self.table(panes,'Largest files',('File','Logical size'))
        self.warnings = self.table(panes,'Scan coverage',('Details',))
        settings = ttk.Frame(self.frame)
        settings.grid(row=6,column=0,sticky='ew',pady=(10,0))
        self.notifications = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings,text='Desktop notifications',variable=self.notifications,command=self.update_notifications).pack(side='left')
        self.autostart = tk.BooleanVar(value=False)
        if not self_test and startup_supported():
            try:
                self.autostart.set(startup_enabled())
            except OSError:
                pass
            ttk.Checkbutton(settings,text='Start with Windows',variable=self.autostart,command=self.update_startup).pack(side='left',padx=10)
        ttk.Label(settings,text='Read-only • alerts after changes',style='Muted.TLabel').pack(side='right')
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
            tree.column(col, width=140 if col in ('Group','Time','Change','Size') else (670 if len(columns)==1 else 220), minwidth=65)
        tree.grid(row=0, column=0, sticky='nsew')
        y = ttk.Scrollbar(frame, command=tree.yview)
        y.grid(row=0, column=1, sticky='ns')
        x = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        x.grid(row=1, column=0, sticky='ew')
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        return tree

    def controls(self):
        locked = self.busy or self.active_root is not None
        self.folder_entry.configure(state='disabled' if locked else 'normal')
        self.browse.configure(state='disabled' if locked else 'normal')
        for key, button in self.buttons.items():
            disabled = (key != 'stop' and self.busy) or (key == 'start' and self.active_root is not None) or (key == 'stop' and self.active_root is None)
            button.configure(state='disabled' if disabled else 'normal')

    def browse_folder(self):
        path = filedialog.askdirectory(parent=self.app)
        if path:
            self.monitor_path.set(path)

    def folder(self):
        if self.active_root is not None:
            return self.active_root
        path = self.monitor_path.get().strip() or self.app.root_path.get().strip() or filedialog.askdirectory(parent=self.app)
        if path:
            self.monitor_path.set(path)
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
        self.monitor_path.set(str(root))
        self.state.set('Monitoring active')
        if not self.app.root_path.get():
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
        self.state.set('Not monitoring')
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
            for value in self.metrics.values():
                value.set('—')
            for tree in (self.alerts, self.history, self.dupes, self.largest, self.warnings):
                self.fill(tree, [])
            self.tabs.tab(self.frame, text='Overview')
            self.display_root = root
        self.busy = True
        self.controls()
        self.status.set(f'Checking {root}…')
        def worker():
            try:
                if kind == 'snapshot':
                    value = SafetyIndex().refresh(root)
                else:
                    warnings = []
                    value = (*duplicates(root, coverage=warnings), warnings)
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
                if self.active_root == root and value.complete:
                    alerts = set(value.alerts)
                    new = alerts - self.previous_alerts
                    self.previous_alerts = alerts
                    if self.notifications.get() and getattr(self.app, 'tray', None):
                        self.app.tray.notify(len(new))
            elif kind == 'duplicates':
                self.render_duplicates(root, value)
            else:
                self.state.set('Check failed')
                self.status.set(f'{root}: {value}')
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
        self.metrics['files'].set(f'{result.files:,}')
        self.metrics['size'].set(f'{result.bytes / 1073741824:,.2f} GiB' if result.bytes >= 1073741824 else f'{result.bytes / 1048576:,.1f} MiB')
        self.metrics['alerts'].set(str(len(result.alerts)) if result.complete else '—')
        self.metrics['changes'].set(str(len(result.history)) if result.complete else '—')
        self.fill(self.alerts, [(source, target, moves.get(target, '')) for source, target in result.alerts[:1000]])
        self.fill(self.history, [(datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S'),a,p,d) for t,a,p,d in result.history])
        self.fill(self.largest, [(path, f'{size / 1048576:,.2f} MiB') for path,size in result.largest])
        self.fill(self.warnings, [(warning,) for warning in result.warnings[:100]])
        self.tabs.tab(self.frame, text=f'Overview ({len(result.alerts)})' if result.complete and result.alerts else 'Overview')
        if result.complete:
            mode = f'Monitoring ({self.wakeup.backend})' if self.active_root is not None and self.wakeup else 'Snapshot complete'
            self.state.set(mode)
            self.status.set(f'{root}  •  {len(result.warnings)} scan warnings  •  Last checked {datetime.now():%H:%M:%S}')
        else:
            self.state.set('Limited coverage')
            self.status.set(f'{root}  •  Partial results; alerts unavailable. See Scan coverage for details.')
            if self.active_root is None:
                self.panes.select(self.largest.master)
            else:
                self.panes.select(self.warnings.master)

    def render_duplicates(self, root, result):
        groups, skipped = result[:2]
        warnings = result[2] if len(result) > 2 else []
        self.panes.select(self.dupes.master)
        self.fill(self.dupes, [(i, p, f'{size:,}') for i,(size,paths) in enumerate(groups,1) for p in paths][:2000])
        self.fill(self.warnings, [(warning,) for warning in warnings])
        extra = sum(size*(len(paths)-1) for size,paths in groups)
        self.status.set(f'{len(groups)} duplicate groups  •  {extra / 1048576:,.1f} MiB additional logical size  •  {skipped} skipped. Review before deleting.')
        if warnings:
            self.state.set('Limited duplicate coverage')
