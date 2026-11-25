"""Explicit preview and confirmation workflow for link repair."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .repair import plan_repair, suggestions, RepairJournal


class RepairView:
    def __init__(self, app, pages, self_test=False):
        self.app = app
        self.frame = ttk.Frame(pages)
        pages.insert(2, self.frame, text='Link repair')
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(4, weight=1)
        self.events = queue.Queue()
        self.busy = False
        self.plan = None
        self.hints = []
        self.log_rows = []
        ttk.Label(self.frame,text='Smart Link Repair',style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text='Preview changes to missing relative links in HTML or JSON. Close external editors before applying or undoing.',style='Muted.TLabel',wraplength=700).grid(row=1,column=0,sticky='w',pady=(4,12))
        form=ttk.Frame(self.frame,style='Card.TFrame',padding=12)
        form.grid(row=2,column=0,sticky='ew')
        form.columnconfigure(1,weight=1)
        self.fields={}
        for i,(key,label) in enumerate([('root','Project folder'),('source','Dependent file'),('old','Missing target'),('new','Replacement file')]):
            var=tk.StringVar()
            self.fields[key]=var
            ttk.Label(form,text=label,style='Card.TLabel').grid(row=i,column=0,sticky='w',padx=(0,10),pady=3)
            ttk.Entry(form,textvariable=var).grid(row=i,column=1,sticky='ew',pady=3)
            if key!='old':
                ttk.Button(form,text='Browse',command=lambda k=key:self.browse(k)).grid(row=i,column=2,padx=(8,0))
            var.trace_add('write',self.invalidate)
        actions=ttk.Frame(self.frame)
        actions.grid(row=3,column=0,sticky='ew',pady=10)
        self.buttons={}
        for key,label,cmd in [('suggest','Find move hints',self.find),('preview','Preview',self.preview),('apply','Apply repair',self.apply),('history','Repair history',self.history),('undo','Undo selected',self.undo)]:
            b=ttk.Button(actions,text=label,command=cmd,style='Accent.TButton' if key=='preview' else 'TButton')
            b.pack(side='left',padx=(0,5))
            self.buttons[key]=b
        self.tabs=ttk.Notebook(self.frame)
        self.tabs.grid(row=4,column=0,sticky='nsew')
        diff=ttk.Frame(self.tabs)
        self.tabs.add(diff,text='Preview')
        diff.columnconfigure(0,weight=1)
        diff.rowconfigure(0,weight=1)
        self.diff=tk.Text(diff,wrap='none',state='disabled',height=8,font='TkFixedFont',padx=10,pady=8)
        self.diff.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(diff,command=self.diff.yview)
        y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(diff,orient='horizontal',command=self.diff.xview)
        x.grid(row=1,column=0,sticky='ew')
        self.diff.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.hint_tree=self.table('Move hints',('source','missing','possible replacement'))
        self.hint_tree.bind('<Double-1>',lambda _:self.use_hint())
        self.log_tree=self.table('History',('id','source','status'))
        self.status=tk.StringVar(value='Choose a project folder or select a broken link in Overview.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=720).grid(row=5,column=0,sticky='ew',pady=8)
        self.controls()
        if not self_test:
            app.after(200,self.poll)

    def table(self,title,columns):
        frame=ttk.Frame(self.tabs)
        self.tabs.add(frame,text=title)
        frame.columnconfigure(0,weight=1)
        frame.rowconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
        for col in columns:
            tree.heading(col,text=col.title())
            tree.column(col,width=75 if col=='id' else 220)
        tree.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(frame,command=tree.yview)
        y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        x.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        return tree

    def invalidate(self,*_):
        self.plan=None
        if hasattr(self,'buttons') and 'apply' in self.buttons:
            self.buttons['apply'].configure(state='disabled')

    def controls(self):
        for key,button in self.buttons.items():
            button.configure(state='disabled' if self.busy or (key=='apply' and self.plan is None) else 'normal')

    def browse(self,key):
        base=self.fields['root'].get() or str(Path.home())
        path=(filedialog.askdirectory(parent=self.app) if key=='root' else
              filedialog.askopenfilename(parent=self.app,initialdir=base))
        if path:
            self.fields[key].set(path)

    def open_link(self,root,source,old,new=''):
        for key,value in zip(('root','source','old','new'),(root,source,old,new)):
            self.fields[key].set(str(value))
        self.app.tabs.select(self.frame)
        self.status.set('Verify the replacement path, then preview. A move hint is not proof of identity.')

    def run(self,kind,operation):
        if self.busy:
            return
        self.busy=True
        self.controls()
        self.status.set('Working…')
        def worker():
            try:
                self.events.put((kind,operation()))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def values(self):
        values=tuple(self.fields[k].get().strip() for k in ('root','source','old','new'))
        if not all(values):
            raise ValueError('Enter all four paths.')
        return values

    def find(self):
        root=self.fields['root'].get().strip() or self.app.safety.monitor_path.get().strip()
        if not root:
            self.status.set('Choose a project folder first.')
            return
        self.fields['root'].set(root)
        self.run('hints',lambda:(root,suggestions(root)))

    def use_hint(self):
        selection=self.hint_tree.selection()
        if selection:
            root,row=self.hints[int(selection[0])]
            self.open_link(root,row['source'],row['old'],row['new'])

    def preview(self):
        try:
            values=self.values()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.plan=None
        self.run('preview',lambda:(values,plan_repair(*values)))

    def render_plan(self,plan):
        self.plan=plan
        self.diff.configure(state='normal')
        self.diff.delete('1.0','end')
        self.diff.insert('1.0',plan.preview())
        self.diff.configure(state='disabled')
        self.tabs.select(self.diff.master)
        self.status.set(f'{plan.replacements} literal link(s) will change. Review the diff before applying.')
        self.controls()

    def apply(self):
        plan=self.plan
        if plan is None or self.busy:
            return
        if not messagebox.askyesno('Apply link repair',f'Modify {plan.source}?\n\nClose external editors first. An original-content copy is saved in the local repair journal. Atomic replacement may change file metadata.',parent=self.app):
            return
        self.plan=None
        self.run('applied',lambda:RepairJournal().apply(plan,plan.token))

    def history(self):
        self.run('history',lambda:RepairJournal().entries())

    def undo(self):
        selection=self.log_tree.selection()
        if not selection:
            self.status.set('Select an entry in Repair history.')
            return
        ident=int(selection[0])
        if messagebox.askyesno('Undo repair','Restore original contents only if the file still exactly matches the repaired version? Close external editors first.',parent=self.app):
            self.run('undone',lambda:RepairJournal().undo(ident))

    def poll(self):
        try:
            kind,value=self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy=False
            if kind=='preview':
                values,plan=value
                try:
                    if self.values()==values:
                        self.render_plan(plan)
                    else:
                        self.status.set('Paths changed. Preview again.')
                except ValueError:
                    self.status.set('Paths changed. Preview again.')
            elif kind=='hints':
                root,rows=value
                self.hints=[(root,row) for row in rows]
                self.hint_tree.delete(*self.hint_tree.get_children())
                for i,row in enumerate(rows):
                    self.hint_tree.insert('','end',iid=str(i),values=(row['source'],row['old'],row['new']))
                self.tabs.select(self.hint_tree.master)
                self.status.set(f'{len(rows)} possible repairs. Double-click a hint to inspect it.')
            elif kind=='history':
                self.log_tree.delete(*self.log_tree.get_children())
                for row in value:
                    self.log_tree.insert('','end',iid=str(row['id']),values=(row['id'],row['source'],row['status']))
                self.tabs.select(self.log_tree.master)
                self.status.set(f'{len(value)} journal entries.')
            elif kind=='applied':
                self.status.set(f'Repair {value} applied. Refresh Overview to check the link again.')
            elif kind=='undone':
                self.status.set(f'Original contents restored: {value}')
            else:
                self.status.set(value)
            self.controls()
        self.app.after(200,self.poll)
