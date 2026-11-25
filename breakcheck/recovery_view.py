"""Desktop recovery: explicit opt-in, bounded version capture, safe copy-out."""
import queue
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .agent import save_preferences
from .recovery import RecoveryStore, MIB


class RecoveryView:
    def __init__(self, app, pages, self_test=False):
        self.app = app
        self.events = queue.Queue()
        self.busy = False
        self.rows = {}
        self.frame = ttk.Frame(pages)
        pages.insert(1, self.frame, text='Recovery')
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)
        ttk.Label(self.frame, text='Smart Recovery', style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text='Save earlier file contents and restore a selected version to a new path.',style='Muted.TLabel',wraplength=720).grid(row=1,column=0,sticky='w',pady=(4,14))
        card = ttk.Frame(self.frame, style='Card.TFrame', padding=14)
        card.grid(row=2,column=0,sticky='ew')
        self.enabled = tk.BooleanVar(value=False)
        self.quota = tk.StringVar(value='256')
        ttk.Checkbutton(card,text='Save versions automatically while monitoring a project',variable=self.enabled,command=self.preferences).grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Label(card,text='Total content limit (MiB)',style='Card.TLabel').grid(row=1,column=0,sticky='w',pady=7)
        ttk.Entry(card,textvariable=self.quota,width=8).grid(row=1,column=1,sticky='w',padx=7)
        ttk.Button(card,text='Save settings',command=self.preferences).grid(row=1,column=2,sticky='w')
        ttk.Label(card,text='Files up to 16 MiB. Older versions are not automatically removed. Local copies are not a full backup.',style='CardCaption.TLabel',wraplength=690).grid(row=2,column=0,columnspan=3,sticky='w')
        actions = ttk.Frame(self.frame)
        actions.grid(row=3,column=0,sticky='ew',pady=12)
        self.buttons = []
        for text, callback, style in [('Capture folder now',self.capture,'Accent.TButton'),('Refresh versions',self.refresh,'TButton'),('Restore selected as…',self.restore,'TButton')]:
            button = ttk.Button(actions,text=text,command=callback,style=style)
            button.pack(side='left',padx=(0,8))
            self.buttons.append(button)
        table = ttk.Frame(self.frame)
        table.grid(row=4,column=0,sticky='nsew')
        table.columnconfigure(0,weight=1)
        table.rowconfigure(0,weight=1)
        self.tree = ttk.Treeview(table,columns=('id','file','root','date','size'),show='headings',selectmode='browse')
        for col,title,width in [('id','Version',65),('file','File',200),('root','Project',220),('date','Saved at',155),('size','Bytes',90)]:
            self.tree.heading(col,text=title)
            self.tree.column(col,width=width,minwidth=55)
        self.tree.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(table,command=self.tree.yview)
        y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(table,orient='horizontal',command=self.tree.xview)
        x.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.status=tk.StringVar(value='No recovery capture requested. Select a folder to save versions, or refresh saved versions.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=730).grid(row=5,column=0,sticky='ew',pady=10)
        if not self_test:
            app.after(200,self.poll)

    def sync_preferences(self):
        prefs = self.app.safety.prefs
        self.enabled.set(prefs.backup)
        self.quota.set(str(prefs.quota_mib))

    def preferences(self):
        prefs = self.app.safety.prefs
        try:
            quota = int(self.quota.get())
            if not 1 <= quota <= 4096:
                raise ValueError('Choose a content limit from 1 to 4096 MiB.')
            if self.enabled.get() and not prefs.backup:
                if not messagebox.askyesno('Enable local recovery','Save copies of regular files in the monitored project? Copies may contain private data and remain on this device until manually removed.',parent=self.app):
                    self.sync_preferences()
                    return
            prefs = replace(prefs,backup=self.enabled.get(),quota_mib=quota)
            save_preferences(prefs)
            self.app.safety.prefs=prefs
            self.status.set('Recovery settings saved. Changes take effect on the next monitoring check.')
        except (OSError,ValueError) as exc:
            self.sync_preferences()
            messagebox.showerror('Recovery settings',str(exc),parent=self.app)

    def run(self, operation):
        if self.busy:
            return
        self.busy=True
        for button in self.buttons:
            button.configure(state='disabled')
        self.status.set('Working…')
        def worker():
            try:
                self.events.put(('ok',operation()))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def capture(self):
        try:
            quota=int(self.quota.get())
            if not 1 <= quota <= 4096:
                raise ValueError('Choose a content limit from 1 to 4096 MiB.')
        except ValueError as exc:
            messagebox.showerror('Recovery',str(exc),parent=self.app)
            return
        folder=filedialog.askdirectory(parent=self.app,initialdir=self.app.safety.monitor_path.get() or str(Path.home()))
        if not folder:
            return
        if not messagebox.askyesno('Capture file versions',f'Save local copies of eligible files in {folder}?',parent=self.app):
            return
        def operation():
            store=RecoveryStore()
            return ('capture',store.capture(folder,quota*MIB),store.versions())
        self.run(operation)

    def refresh(self):
        self.run(lambda: ('list',RecoveryStore().versions()))

    def restore(self):
        selected=self.tree.selection()
        if not selected:
            messagebox.showinfo('Recovery','Select a saved version first.',parent=self.app)
            return
        row=self.rows[selected[0]]
        original=Path(row['root']) / row['path']
        destination=filedialog.asksaveasfilename(parent=self.app,title='Restore to a new file (no overwrite)',initialdir=str(original.parent if original.parent.is_dir() else Path.home()),initialfile=original.name)
        if destination:
            self.run(lambda: ('restored',RecoveryStore().restore(row['id'],destination)))

    def render_versions(self, rows):
        self.rows={}
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            key=str(row['id'])
            self.rows[key]=row
            date=datetime.fromtimestamp(row['captured']/1e9).strftime('%Y-%m-%d %H:%M:%S')
            self.tree.insert('','end',iid=key,values=(key,row['path'],row['root'],date,f'{row["size"]:,}'))

    def render_capture(self, result, rows):
        self.render_versions(rows)
        warning=' ' + ' '.join((result.warnings or [])[-2:]) if result.warnings else ''
        self.status.set(f'{result.saved} new versions • {result.unchanged} unchanged • {result.skipped} skipped • {result.used/MIB:.1f}/{result.quota/MIB:.0f} MiB saved content.{warning}')

    def poll(self):
        try:
            kind,value=self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy=False
            for button in self.buttons:
                button.configure(state='normal')
            if kind=='error':
                self.status.set(value)
            elif value[0]=='capture':
                self.render_capture(value[1],value[2])
            elif value[0]=='list':
                self.render_versions(value[1])
                self.status.set(f'{len(value[1])} latest saved versions.')
            else:
                self.status.set(f'Restored to {value[1]}.')
        self.app.after(200,self.poll)
