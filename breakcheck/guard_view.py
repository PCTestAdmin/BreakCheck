"""Explicit guarded operation and optional update check."""
import json
import queue
import threading
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser
from .guard import preview, apply, rules, set_rule, remove_rule
from .updates import check_update, RELEASES
from .agent import save_preferences


class GuardView:
    def __init__(self, app, pages, self_test=False):
        self.app=app
        self.frame=ttk.Frame(pages)
        pages.insert(1,self.frame,text='Protection')
        self.frame.columnconfigure(0,weight=1)
        self.frame.rowconfigure(3,weight=1)
        self.events=queue.Queue()
        self.busy=False
        self.plan=None
        self.rule_rows=[]
        ttk.Label(self.frame,text='Active Protection',style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text='Rules apply only to guided operations inside BreakCheck, not Windows Explorer or other apps.',style='Muted.TLabel',wraplength=720).grid(row=1,column=0,sticky='w',pady=(3,10))
        form=ttk.Frame(self.frame,style='Card.TFrame',padding=10)
        form.grid(row=2,column=0,sticky='ew')
        form.columnconfigure(1,weight=1)
        self.fields={k:tk.StringVar() for k in ('root','source','destination')}
        self.operation=tk.StringVar(value='move')
        for i,(key,label) in enumerate([('root','Project'),('source','File'),('destination','New path')]):
            ttk.Label(form,text=label,style='Card.TLabel').grid(row=i,column=0,sticky='w',padx=(0,8),pady=3)
            ttk.Entry(form,textvariable=self.fields[key]).grid(row=i,column=1,sticky='ew',pady=3)
            ttk.Button(form,text='Browse',command=lambda k=key:self.browse(k)).grid(row=i,column=2,padx=5)
            self.fields[key].trace_add('write',self.invalidate)
        choices=ttk.Combobox(form,textvariable=self.operation,values=('move','rename','delete'),state='readonly',width=12)
        choices.grid(row=3,column=0,sticky='w')
        self.operation.trace_add('write',self.invalidate)
        buttons=ttk.Frame(form,style='Card.TFrame')
        buttons.grid(row=3,column=1,columnspan=2,sticky='e',pady=4)
        self.preview_button=ttk.Button(buttons,text='Check risks',command=self.check,style='Accent.TButton')
        self.preview_button.pack(side='left',padx=5)
        self.apply_button=ttk.Button(buttons,text='Confirm move',command=self.execute,state='disabled')
        self.apply_button.pack(side='left')
        self.tabs=ttk.Notebook(self.frame)
        self.tabs.grid(row=3,column=0,sticky='nsew',pady=8)
        detail=ttk.Frame(self.tabs)
        self.tabs.add(detail,text='Risk review')
        detail.rowconfigure(0,weight=1)
        detail.columnconfigure(0,weight=1)
        self.text=tk.Text(detail,wrap='word',state='disabled',height=10,padx=10,pady=10)
        self.text.grid(row=0,column=0,sticky='nsew')
        bar=ttk.Scrollbar(detail,command=self.text.yview)
        bar.grid(row=0,column=1,sticky='ns')
        self.text.configure(yscrollcommand=bar.set)
        rulepage=ttk.Frame(self.tabs)
        self.tabs.add(rulepage,text='Protection rules')
        rulepage.rowconfigure(1,weight=1)
        rulepage.columnconfigure(0,weight=1)
        tools=ttk.Frame(rulepage)
        tools.grid(row=0,column=0,sticky='ew')
        for label,command in [('Block file',lambda:self.add_rule('block',False)),('Block folder',lambda:self.add_rule('block',True)),('Warn folder',lambda:self.add_rule('warn',True)),('Remove',self.remove),('Refresh',self.refresh)]:
            ttk.Button(tools,text=label,command=command).pack(side='left',padx=3)
        self.tree=ttk.Treeview(rulepage,columns=('mode','path'),show='headings',selectmode='browse')
        for col,width in [('mode',85),('path',550)]:
            self.tree.heading(col,text=col.title())
            self.tree.column(col,width=width)
        self.tree.grid(row=1,column=0,sticky='nsew')
        y=ttk.Scrollbar(rulepage,command=self.tree.yview)
        y.grid(row=1,column=1,sticky='ns')
        self.tree.configure(yscrollcommand=y.set)
        footer=ttk.Frame(self.frame)
        footer.grid(row=4,column=0,sticky='ew')
        self.auto=tk.BooleanVar(value=False)
        ttk.Checkbutton(footer,text='Check for updates at startup',variable=self.auto,command=self.save_auto).pack(side='left')
        self.update_button=ttk.Button(footer,text='Check updates',command=self.update)
        self.update_button.pack(side='right')
        ttk.Button(footer,text='Releases',command=lambda:webbrowser.open(RELEASES)).pack(side='right',padx=5)
        self.status=tk.StringVar(value='Select a file and a project. Delete checks are advisory only.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=730).grid(row=5,column=0,sticky='ew',pady=5)
        if not self_test:
            app.after(200,self.poll)

    def resume(self):
        self.auto.set(self.app.safety.prefs.auto_updates)
        self.refresh()
        if self.auto.get():
            self.update()

    def save_auto(self):
        try:
            prefs=replace(self.app.safety.prefs,auto_updates=self.auto.get())
            save_preferences(prefs)
            self.app.safety.prefs=prefs
        except OSError as exc:
            self.auto.set(self.app.safety.prefs.auto_updates)
            self.status.set(str(exc))

    def update(self):
        self.update_button.configure(state='disabled')
        def worker():
            try:
                self.events.put(('update',check_update()))
            except Exception as exc:
                self.events.put(('update-error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def invalidate(self,*_):
        self.plan=None
        if hasattr(self,'apply_button'):
            self.apply_button.configure(state='disabled')

    def open_file(self,root,source):
        self.fields['root'].set(str(root))
        self.fields['source'].set(str(source))
        self.fields['destination'].set('')
        self.operation.set('move')
        self.app.tabs.select(self.frame)

    def browse(self,key):
        base=self.fields['root'].get() or str(Path.home())
        if key=='root':
            value=filedialog.askdirectory(parent=self.app,initialdir=base)
        elif key=='source':
            value=filedialog.askopenfilename(parent=self.app,initialdir=base)
        else:
            value=filedialog.asksaveasfilename(parent=self.app,initialdir=base)
        if value:
            self.fields[key].set(value)

    def values(self):
        root,source,dest=(self.fields[k].get().strip() for k in ('root','source','destination'))
        op=self.operation.get()
        if not root or not source or (op!='delete' and not dest):
            raise ValueError('Choose project, file and destination (except delete review).')
        return root,source,op,dest if op!='delete' else None

    def run(self,kind,task):
        if self.busy:
            return
        self.busy=True
        self.preview_button.configure(state='disabled')
        self.apply_button.configure(state='disabled')
        self.status.set('Working…')
        def worker():
            try:
                self.events.put((kind,task()))
            except Exception as exc:
                self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def check(self):
        try:
            values=self.values()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.invalidate()
        self.run('plan',lambda:(values,preview(*values)))

    def render_plan(self,plan):
        self.plan=plan
        ev=plan.evidence
        data=[f"{plan.operation.upper()}: {plan.source}",f"Destination: {plan.destination or '—'}",
              f"Direct references: {len(ev['direct'])} | Indirect: {len(ev['indirect'])}",
              'BLOCKED by rule' if ev['blocked'] else 'Review required',
              ev['notice'],'','Matching rules:']
        data.extend(f"{r['mode'].upper()}: {r['path']}" for r in ev['rules'])
        data.append('Affected references:')
        data.extend(f"{r['source']} → {r['target']} ({r['kind']})" for r in ev['direct'][:200])
        data.append('Coverage: '+json.dumps(ev['coverage'],ensure_ascii=False,indent=2))
        self.text.configure(state='normal')
        self.text.delete('1.0','end')
        self.text.insert('1.0','\n'.join(data))
        self.text.configure(state='disabled')
        self.tabs.select(self.text.master)
        self.apply_button.configure(state='normal' if ev['executable'] else 'disabled')
        self.status.set('Review risks and close external editors before moving. Delete is advisory only.')

    def execute(self):
        plan=self.plan
        if plan is None or self.busy:
            return
        if messagebox.askyesno('Confirm guarded move',f'Move {plan.source} to {plan.destination}?\n\nDetected dependencies may break. Close external editors. No destination is overwritten.',parent=self.app):
            self.invalidate()
            self.run('moved',lambda:apply(plan,plan.token))

    def refresh(self):
        try:
            self.rule_rows=rules()
            self.tree.delete(*self.tree.get_children())
            for i,row in enumerate(self.rule_rows):
                self.tree.insert('','end',iid=str(i),values=(row['mode'],row['path']))
        except (OSError,ValueError) as exc:
            self.status.set(str(exc))

    def add_rule(self,mode,folder):
        path=(filedialog.askdirectory(parent=self.app) if folder else filedialog.askopenfilename(parent=self.app))
        if path:
            try:
                set_rule(path,mode)
                self.invalidate()
                self.refresh()
            except (OSError,ValueError) as exc:
                self.status.set(str(exc))

    def remove(self):
        selected=self.tree.selection()
        if selected and messagebox.askyesno('Remove rule','Remove selected local protection rule?',parent=self.app):
            try:
                remove_rule(self.rule_rows[int(selected[0])]['path'])
                self.invalidate()
                self.refresh()
            except (OSError,ValueError) as exc:
                self.status.set(str(exc))

    def poll(self):
        try:
            kind,value=self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            if kind.startswith('update'):
                self.update_button.configure(state='normal')
                if kind=='update':
                    self.status.set(f"Update available: {value['latest']}. Open Releases." if value['available'] else 'No newer release found.')
                    if value['available']:
                        self.app.status.set(f"BreakCheck {value['latest']} available — open Protection / Releases.")
                else:
                    self.status.set(f'Update check failed: {value}')
            else:
                self.busy=False
                self.preview_button.configure(state='normal')
                if kind=='plan':
                    values,plan=value
                    try:
                        if self.values()==values:
                            self.render_plan(plan)
                        else:
                            self.status.set('Paths changed. Check risks again.')
                    except ValueError:
                        self.status.set('Paths changed. Check risks again.')
                elif kind=='moved':
                    self.status.set(f'Moved to {value}. Check Overview for broken links.')
                else:
                    self.status.set(str(value))
        self.app.after(200,self.poll)
