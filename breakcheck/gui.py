"""Native desktop interface using Python's standard Tk toolkit."""
from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from .core import scan, analyze
from .views import InsightsView, apply_theme


class App(tk.Tk):
    def __init__(self, self_test=False):
        super().__init__()
        if self_test:
            self.withdraw()
        self.title('BreakCheck — File dependency inspector')
        self.geometry('1050x700')
        self.minsize(760, 550)
        self.root_path = tk.StringVar()
        self.target = tk.StringVar()
        self.destination = tk.StringVar()
        self.operation = tk.StringVar(value='delete')
        self.status = tk.StringVar(value='Choose a scan folder and an existing target.')
        self.events = queue.Queue()
        self.report = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        header = ttk.Frame(self, padding=(20, 16))
        header.grid(row=0, column=0, sticky='ew')
        self.dark = tk.BooleanVar(value=False)
        ttk.Checkbutton(header, text='Dark mode', variable=self.dark, command=lambda: apply_theme(self, self.dark.get())).pack(side='right', anchor='n')
        ttk.Label(header, text='BreakCheck', font=('TkDefaultFont', 23, 'bold')).pack(anchor='w')
        ttk.Label(header, text='Know what breaks before you break it.').pack(anchor='w')
        ttk.Label(header, text='READ-ONLY SIMULATION • No scanned files are changed.').pack(anchor='w', pady=(5, 0))
        form = ttk.Frame(self, padding=(20, 0, 20, 10))
        form.grid(row=1, column=0, sticky='ew')
        form.columnconfigure(1, weight=1)
        self.controls = []
        for row, (label, var) in enumerate([('Scan folder', self.root_path), ('Target path', self.target), ('Destination', self.destination)]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=4)
            entry = ttk.Entry(form, textvariable=var)
            entry.grid(row=row, column=1, sticky='ew', pady=4)
            self.controls.append(entry)
            if row == 0:
                button = ttk.Button(form, text='Browse folder', command=self.choose_root)
                button.grid(row=row, column=2, padx=5)
                self.controls.append(button)
            elif row == 1:
                for col, label, folder in [(2, 'Browse file', False), (3, 'Browse folder', True)]:
                    button = ttk.Button(form, text=label, command=lambda f=folder: self.choose_target(f))
                    button.grid(row=row, column=col, padx=5)
                    self.controls.append(button)
            else:
                self.dest_entry = entry
        ttk.Label(form, text='Operation').grid(row=3, column=0, sticky='w')
        choice = ttk.Combobox(form, textvariable=self.operation, values=('delete', 'move', 'rename'), state='readonly', width=12)
        choice.grid(row=3, column=1, sticky='w', pady=4)
        choice.bind('<<ComboboxSelected>>', lambda _: self.sync_destination())
        self.controls.append(choice)
        self.run_button = ttk.Button(form, text='Analyze impact', command=self.start)
        self.run_button.grid(row=3, column=2, columnspan=2, sticky='ew', padx=5)
        self.summary = ttk.Label(self, text='No scan performed.', padding=(20, 8), font=('TkDefaultFont', 12, 'bold'))
        self.summary.grid(row=2, column=0, sticky='ew')
        tabs = ttk.Notebook(self)
        tabs.grid(row=3, column=0, sticky='nsew', padx=20, pady=8)
        results = ttk.Frame(tabs)
        tabs.add(results, text='Potential impact')
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(results, columns=('level', 'source', 'reference', 'detail'), show='headings')
        for col, title, width in [('level', 'Impact', 90), ('source', 'Dependent file', 260), ('reference', 'Referenced path', 240), ('detail', 'Reason / evidence', 350)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=70, stretch=col != 'level')
        self.tree.grid(row=0, column=0, sticky='nsew')
        vbar = ttk.Scrollbar(results, command=self.tree.yview)
        vbar.grid(row=0, column=1, sticky='ns')
        hbar = ttk.Scrollbar(results, orient='horizontal', command=self.tree.xview)
        hbar.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        details = ttk.Frame(tabs)
        tabs.add(details, text='Coverage & warnings')
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.coverage = tk.Text(details, wrap='word', state='disabled', padx=10, pady=10)
        self.coverage.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(details, command=self.coverage.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.coverage.configure(yscrollcommand=scroll.set)
        self.insights = InsightsView(tabs)
        footer = ttk.Frame(self, padding=(20, 8, 20, 16))
        footer.grid(row=4, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, wraplength=650).grid(row=0, column=0, sticky='w')
        self.export = ttk.Button(footer, text='Export JSON report', command=self.save, state='disabled')
        self.export.grid(row=0, column=1, sticky='e')
        self.sync_destination()
        apply_theme(self, False)
        if not self_test:
            self.after(100, self.poll)

    def sync_destination(self):
        self.dest_entry.configure(state='disabled' if self.operation.get() == 'delete' else 'normal')

    def choose_root(self):
        value = filedialog.askdirectory()
        if value:
            self.root_path.set(value)
            selected = self.target.get().strip()
            if selected and not Path(selected).resolve().is_relative_to(Path(value).resolve()):
                self.target.set('')

    def choose_target(self, folder):
        options = {'initialdir': self.root_path.get() or str(Path.home())}
        value = filedialog.askdirectory(**options) if folder else filedialog.askopenfilename(**options)
        if value:
            self.target.set(value)

    def start(self):
        root, target, dest = (v.get().strip() for v in (self.root_path, self.target, self.destination))
        operation = self.operation.get()
        if not root or not target or (operation != 'delete' and not dest):
            messagebox.showwarning('Missing path', 'Choose a scan folder, target and destination when required.')
            return
        self.report = None
        self.insights.clear()
        self.coverage.configure(state='normal')
        self.coverage.delete('1.0', 'end')
        self.coverage.configure(state='disabled')
        self.export.configure(state='disabled')
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.summary.configure(text='Analyzing references…')
        self.status.set('Scanning local files. No changes will be made.')
        self.run_button.configure(state='disabled')
        for control in self.controls:
            control.configure(state='disabled')
        def worker():
            try:
                index = scan(root)
                self.events.put(('report', analyze(index, index.root / target, operation, index.root / dest if operation != 'delete' else None)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, value = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            for control in self.controls:
                control.configure(state='readonly' if isinstance(control, ttk.Combobox) else 'normal')
            self.sync_destination()
            self.run_button.configure(state='normal')
            if kind == 'error':
                self.summary.configure(text='Scan failed')
                self.status.set(value)
                messagebox.showerror('Scan failed', value)
            else:
                self.render(value)
        self.after(100, self.poll)

    def render(self, report):
        self.report = report
        self.insights.render(report)
        self.summary.configure(text=f'{len(report.direct)} direct references • {len(report.indirect)} indirect dependents')
        def relative(path):
            return str(path.relative_to(report.scan.root)) if path.is_relative_to(report.scan.root) else str(path)
        for impact in report.direct:
            ref = impact.reference
            self.tree.insert('', 'end', values=('Direct', relative(ref.source), relative(ref.target), f'{ref.kind}{":" + str(ref.line) if ref.line else ""} | {impact.reason}'))
        for source in report.indirect:
            self.tree.insert('', 'end', values=('Indirect', relative(source), '—', 'Depends on a potentially affected file'))
        s = report.scan
        self.coverage.configure(state='normal')
        self.coverage.delete('1.0', 'end')
        self.coverage.insert('end', f'Scan root: {s.root}\nOperation: {report.operation}\nTarget: {report.target}\nDestination: {report.destination or "—"}\n\nFiles seen: {s.files_seen}\nParsed: {s.files_parsed}\nUnsupported: {s.unsupported}\nSkipped entries: {s.skipped}\n\nOnly supported, existing references inside the selected folder are indexed. Dynamic, external, and unsupported references may be missed. No detected references does not prove safety.\n\nWarnings:\n' + ('\n'.join(s.warnings) or 'No parser warnings.'))
        self.coverage.configure(state='disabled')
        self.status.set('Analysis complete. No changes made. No detected references does not prove safety.')
        self.export.configure(state='normal')

    def save(self):
        if self.report is None:
            return
        name = filedialog.asksaveasfilename(defaultextension='.json', initialfile='breakcheck-report.json', filetypes=[('JSON report', '*.json')])
        if name:
            try:
                # Exclusive creation avoids overwriting any scanned file.
                with open(name, 'x', encoding='utf-8') as stream:
                    json.dump(self.report.as_dict(), stream, indent=2)
                self.status.set(f'Report exported: {name}')
            except OSError as exc:
                messagebox.showerror('Export failed', str(exc))


def launch():
    App().mainloop()
