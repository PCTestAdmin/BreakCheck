"""Interactive storage workspace; scans and exports never change source files."""
from pathlib import Path
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .storage import analyze_storage, human_size, MIB


class StorageView:
    def __init__(self, app, pages, self_test=False):
        self.app=app
        self.frame=ttk.Frame(pages)
        pages.insert(1,self.frame,text='Storage')
        self.frame.columnconfigure(0,weight=1)
        self.frame.rowconfigure(5,weight=1)
        self.report=None
        self.events=queue.Queue()
        self.stop=threading.Event()
        self.busy=False
        self.back_stack=[]
        self.chart_rows=[]
        ttk.Label(self.frame,text='Storage Intelligence',style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text='Explore logical file sizes and review large, long-unmodified files.',style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(4,10))
        controls=ttk.Frame(self.frame,style='Card.TFrame',padding=10)
        controls.grid(row=2,column=0,sticky='ew')
        controls.columnconfigure(0,weight=1)
        self.path=tk.StringVar()
        self.older=tk.StringVar(value='180')
        self.minimum=tk.StringVar(value='100')
        self.path_entry=ttk.Entry(controls,textvariable=self.path)
        self.path_entry.grid(row=0,column=0,sticky='ew',padx=(0,8))
        self.browse_button=ttk.Button(controls,text='Browse',command=self.browse)
        self.browse_button.grid(row=0,column=1,padx=(0,6))
        self.scan_button=ttk.Button(controls,text='Scan storage',style='Accent.TButton',command=self.scan)
        self.scan_button.grid(row=0,column=2,padx=(0,6))
        self.cancel_button=ttk.Button(controls,text='Cancel',command=lambda:self.stop.set())
        self.cancel_button.grid(row=0,column=3)
        filters=ttk.Frame(controls,style='Card.TFrame')
        filters.grid(row=1,column=0,columnspan=4,sticky='ew',pady=(8,0))
        ttk.Label(filters,text='Review files at least',style='Card.TLabel').pack(side='left')
        ttk.Entry(filters,textvariable=self.minimum,width=7).pack(side='left',padx=5)
        ttk.Label(filters,text='MiB and',style='Card.TLabel').pack(side='left')
        ttk.Entry(filters,textvariable=self.older,width=7).pack(side='left',padx=5)
        ttk.Label(filters,text='days since modification',style='Card.TLabel').pack(side='left')
        self.metrics={}
        metrics=ttk.Frame(self.frame)
        metrics.grid(row=3,column=0,sticky='ew',pady=10)
        for i,(key,label) in enumerate([('size','Observed size'),('files','Files'),('free','Volume free')]):
            metrics.columnconfigure(i,weight=1,uniform='storage')
            card=ttk.Frame(metrics,style='Card.TFrame',padding=10)
            card.grid(row=0,column=i,sticky='nsew',padx=(0,8) if i<2 else 0)
            ttk.Label(card,text=label,style='CardCaption.TLabel').pack(anchor='w')
            val=tk.StringVar(value='—')
            self.metrics[key]=val
            ttk.Label(card,textvariable=val,style='Metric.TLabel').pack(anchor='w')
        actions=ttk.Frame(self.frame)
        actions.grid(row=4,column=0,sticky='ew',pady=(0,8))
        self.back_button=ttk.Button(actions,text='Back',command=self.back)
        self.back_button.pack(side='left',padx=(0,6))
        self.mode=tk.StringVar(value='Folders')
        mode=ttk.Combobox(actions,textvariable=self.mode,values=('Folders','File types','Modified age'),state='readonly',width=16)
        mode.pack(side='left')
        mode.bind('<<ComboboxSelected>>',lambda _:self.draw())
        self.export_button=ttk.Button(actions,text='Export JSON',command=self.export)
        self.export_button.pack(side='right')
        self.tabs=ttk.Notebook(self.frame)
        self.tabs.grid(row=5,column=0,sticky='nsew')
        chart=ttk.Frame(self.tabs)
        self.tabs.add(chart,text='Distribution')
        chart.columnconfigure(0,weight=1)
        chart.rowconfigure(0,weight=1)
        self.canvas=tk.Canvas(chart,highlightthickness=0,height=230)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        self.canvas.bind('<Configure>',lambda _:self.draw())
        self.canvas.bind('<Button-1>',self.chart_click)
        self.detail=tk.StringVar(value='Click a folder bar to explore its contents.')
        ttk.Label(chart,textvariable=self.detail,style='Muted.TLabel',wraplength=700).grid(row=1,column=0,sticky='ew',pady=5)
        self.largest=self.table('Largest files',('File','Size','Modified days ago','Hard links'))
        self.review=self.table('Review candidates',('File','Size','Modified days ago','Hard links'))
        self.warnings=self.table('Coverage',('Details',))
        self.largest.bind('<Double-1>',lambda _:self.inspect(self.largest))
        self.review.bind('<Double-1>',lambda _:self.inspect(self.review))
        self.status=tk.StringVar(value='Select a folder or drive. No file contents are read.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=740).grid(row=6,column=0,sticky='ew',pady=8)
        self.controls()
        if not self_test:
            app.after(200,self.poll)

    def table(self,title,columns):
        page=ttk.Frame(self.tabs)
        self.tabs.add(page,text=title)
        page.columnconfigure(0,weight=1)
        page.rowconfigure(0,weight=1)
        tree=ttk.Treeview(page,columns=columns,show='headings',selectmode='browse')
        for col in columns:
            tree.heading(col,text=col)
            tree.column(col,width=690 if len(columns)==1 else (340 if col=='File' else 130))
        tree.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(page,command=tree.yview)
        y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(page,orient='horizontal',command=tree.xview)
        x.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        return tree

    def controls(self):
        for widget in (self.path_entry,self.browse_button,self.scan_button):
            widget.configure(state='disabled' if self.busy else 'normal')
        self.cancel_button.configure(state='normal' if self.busy else 'disabled')
        self.back_button.configure(state='normal' if self.back_stack and not self.busy else 'disabled')
        self.export_button.configure(state='normal' if self.report is not None and not self.busy else 'disabled')

    def browse(self):
        path=filedialog.askdirectory(parent=self.app)
        if path:
            self.path.set(path)

    def scan(self,drill=False):
        if self.busy:
            return
        root=self.path.get().strip() or self.app.safety.monitor_path.get().strip()
        if not root:
            self.browse()
            root=self.path.get().strip()
        if not root:
            return
        try:
            days,minimum=int(self.older.get()),int(self.minimum.get())
            if not 0<=days<=36500 or not 0<=minimum<=10**9:
                raise ValueError('Enter non-negative review filters within the supported range.')
        except ValueError as exc:
            self.status.set(str(exc))
            return
        if not drill:
            self.back_stack.clear()
        self.path.set(root)
        self.stop=threading.Event()
        self.busy=True
        self.controls()
        self.status.set('Scanning filesystem metadata…')
        stop=self.stop
        def worker():
            try:
                report=analyze_storage(root,older_days=days,min_bytes=minimum*MIB,stop=stop,
                                       progress=lambda *p:self.events.put(('progress',p)))
                self.events.put(('report',report))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def back(self):
        if self.back_stack and not self.busy:
            self.path.set(self.back_stack.pop())
            self.scan(drill=True)

    def chart_click(self,event):
        if self.busy or self.report is None:
            return
        for top,bottom,row in self.chart_rows:
            if top<=event.y<=bottom:
                self.detail.set(f'{row["name"]}: {human_size(row["bytes"])} • {row["files"]:,} files')
                if self.mode.get()=='Folders' and row.get('directory',False):
                    child=Path(self.report.root)/row['name']
                    try:
                        if child.resolve(strict=True)!=child or not child.is_dir():
                            return
                    except OSError:
                        return
                    self.back_stack.append(self.report.root)
                    self.path.set(str(child))
                    self.scan(drill=True)
                return

    def draw(self):
        self.canvas.delete('all')
        dark=self.app.dark.get()
        bg,fg,track=('#1c2636','#edf2f7','#344258') if dark else ('#ffffff','#172338','#e2e8f0')
        self.canvas.configure(background=bg)
        self.chart_rows=[]
        if self.report is None:
            self.canvas.create_text(16,20,text='Scan a folder to see its distribution.',fill=fg,anchor='nw')
            return
        rows=getattr(self.report,{'Folders':'folders','File types':'categories','Modified age':'ages'}[self.mode.get()])
        width=max(300,self.canvas.winfo_width())
        height=max(100,self.canvas.winfo_height())
        count=max(1,min(12,(height-20)//30))
        positive=[r for r in rows if r['files']]
        visible=positive[:count]
        maximum=max((r['bytes'] for r in visible),default=1) or 1
        bar_start=min(220,width*.35)
        bar_end=max(bar_start+10,width-105)
        for i,row in enumerate(visible):
            y=10+i*30
            name=row['name']
            name=name if len(name)<=27 else name[:24]+'…'
            self.canvas.create_text(10,y+12,text=name,fill=fg,anchor='w')
            self.canvas.create_rectangle(bar_start,y+4,bar_end,y+22,fill=track,outline='')
            self.canvas.create_rectangle(bar_start,y+4,bar_start+(bar_end-bar_start)*row['bytes']/maximum,y+22,fill='#3b82f6',outline='')
            self.canvas.create_text(width-8,y+12,text=human_size(row['bytes']),fill=fg,anchor='e')
            self.chart_rows.append((y,y+28,row))
        if not visible:
            self.canvas.create_text(16,20,text='No regular files observed.',fill=fg,anchor='nw')
        self.detail.set(f'Showing {len(visible)} of {len(positive)} groups. '+('Click a folder to scan it.' if self.mode.get()=='Folders' else 'Click a bar for details.'))

    def render(self,report):
        self.report=report
        self.path.set(report.root)
        self.metrics['size'].set(human_size(report.logical_bytes))
        self.metrics['files'].set(f'{report.files:,}')
        self.metrics['free'].set(human_size(report.volume['free']) if report.volume else '—')
        for tree,rows in ((self.largest,report.largest),(self.review,report.review)):
            tree.delete(*tree.get_children())
            for i,row in enumerate(rows):
                tree.insert('','end',iid=str(i),values=(row['path'],human_size(row['bytes']),row['modified_days_ago'],row['hard_links']))
        self.warnings.delete(*self.warnings.get_children())
        for warning in report.warnings:
            self.warnings.insert('','end',values=(warning,))
        self.draw()
        label='Cancelled' if report.cancelled else 'Scan complete' if report.complete else 'Partial scan'
        self.status.set(f'{label} • {report.entries:,} entries • {report.skipped:,} skipped. Sizes are logical, not reclaimable space. Double-click a file to inspect dependencies.')
        self.controls()

    def inspect(self,tree):
        selected=tree.selection()
        if selected and self.report is not None and not self.busy:
            rows=self.report.largest if tree is self.largest else self.report.review
            relative=rows[int(selected[0])]['path']
            self.app.root_path.set(self.report.root)
            self.app.target.set(str(Path(self.report.root)/relative))
            self.app.tabs.select(self.app.impact_tab)
            self.app.status.set('Review the scan scope, then choose Analyze impact. Age and size do not prove safety.')

    def export(self):
        if self.report is None or self.busy:
            return
        path=filedialog.asksaveasfilename(parent=self.app,defaultextension='.json',initialfile='breakcheck-storage.json')
        if path:
            try:
                with open(path,'x',encoding='utf-8') as stream:
                    json.dump(self.report.as_dict(),stream,indent=2)
                self.status.set(f'Exported {path}')
            except OSError as exc:
                messagebox.showerror('Export',str(exc),parent=self.app)

    def poll(self):
        while True:
            try:
                kind,value=self.events.get_nowait()
            except queue.Empty:
                break
            if kind=='progress':
                self.status.set(f'Scanning… {value[0]:,} entries • {value[1]:,} files • {human_size(value[2])}')
            else:
                self.busy=False
                if kind=='report':
                    self.render(value)
                else:
                    self.status.set(f'Scan failed: {value}')
                    self.controls()
        self.app.after(200,self.poll)
