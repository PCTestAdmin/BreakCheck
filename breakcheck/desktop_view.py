"""First-run guidance and a central settings workspace."""
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import webbrowser

from .agent import save_preferences, Wakeup
from .views import apply_theme
from .tray import startup_supported
from . import __version__

REPO='https://github.com/PCTestAdmin/BreakCheck'

class SettingsView:
    def __init__(self,app,pages):
        self.app=app
        self.frame=ttk.Frame(pages)
        pages.add(self.frame,text='Settings')
        self.frame.columnconfigure(0,weight=1)
        ttk.Label(self.frame,text='Settings',style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text='Manage appearance, monitoring and optional connectivity.',style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(4,14))
        self.interval=tk.StringVar(value='60')
        self.events=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='Changes to monitoring apply after the current check.')
        appearance=self.section(2,'Appearance & startup')
        ttk.Checkbutton(appearance,text='Dark appearance',variable=app.dark,command=self.save_theme).pack(anchor='w',pady=3)
        if startup_supported():
            ttk.Checkbutton(appearance,text='Start with Windows',variable=app.safety.autostart,command=app.safety.update_startup).pack(anchor='w',pady=3)
        else:
            ttk.Label(appearance,text='Windows autostart is available in the packaged Windows desktop app.',style='CardCaption.TLabel',wraplength=680).pack(anchor='w')
        monitor=self.section(3,'Monitoring')
        ttk.Checkbutton(monitor,text='Desktop notifications (Windows tray)',variable=app.safety.notifications,command=app.safety.update_notifications).pack(anchor='w',pady=2)
        ttk.Checkbutton(monitor,text='Use filesystem events when available',variable=self.events).pack(anchor='w',pady=2)
        line=ttk.Frame(monitor,style='Card.TFrame')
        line.pack(fill='x',pady=3)
        ttk.Label(line,text='Full scan interval (seconds, 15–3600)',style='Card.TLabel').pack(side='left')
        ttk.Entry(line,textvariable=self.interval,width=8).pack(side='left',padx=8)
        ttk.Button(line,text='Save monitoring',command=self.save_monitoring).pack(side='left')
        ttk.Label(monitor,text='Event bursts are coalesced; at least 10 seconds between automatic event-triggered scans.',style='CardCaption.TLabel',wraplength=670).pack(anchor='w')
        privacy=self.section(4,'Privacy & recovery')
        ttk.Checkbutton(privacy,text='Check for updates at startup (contacts GitHub)',variable=app.guard.auto,command=app.guard.save_auto).pack(anchor='w',pady=2)
        line=ttk.Frame(privacy,style='Card.TFrame')
        line.pack(fill='x',pady=3)
        ttk.Button(line,text='Recovery settings',command=lambda:pages.select(app.recovery.frame)).pack(side='left',padx=(0,8))
        ttk.Button(line,text='Protection rules',command=lambda:pages.select(app.guard.frame)).pack(side='left')
        ttk.Label(privacy,text='Fleet reporting and local content backups are opt-in. No system-wide operation interception.',style='CardCaption.TLabel',wraplength=680).pack(anchor='w')
        links=ttk.Frame(self.frame)
        links.grid(row=5,column=0,sticky='ew',pady=8)
        for text,callback in [('Getting started',lambda:pages.select(app.welcome.frame)),('Documentation',lambda:webbrowser.open(REPO+'/blob/main/README.md')),('Check updates',self.check_updates),('Report issue',lambda:webbrowser.open(REPO+'/issues'))]:
            ttk.Button(links,text=text,command=callback).pack(side='left',padx=(0,5))
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=730).grid(row=6,column=0,sticky='ew')
        self.frame.bind('<<PageSelected>>',lambda _:self.sync())

    def check_updates(self):
        self.app.tabs.select(self.app.guard.frame)
        self.app.guard.update()

    def section(self,row,title):
        card=ttk.Frame(self.frame,style='Card.TFrame',padding=10)
        card.grid(row=row,column=0,sticky='ew',pady=(0,8))
        ttk.Label(card,text=title,style='Card.TLabel',font=('TkDefaultFont',11,'bold')).pack(anchor='w',pady=(0,4))
        return card

    def sync(self):
        prefs=self.app.safety.prefs
        self.interval.set(str(prefs.desktop_interval))
        self.events.set(prefs.desktop_events)

    def resume(self):
        self.app.dark.set(self.app.safety.prefs.dark)
        apply_theme(self.app,self.app.dark.get())
        self.sync()

    def save_theme(self):
        old=self.app.safety.prefs
        try:
            prefs=replace(old,dark=self.app.dark.get())
            save_preferences(prefs)
            self.app.safety.prefs=prefs
            apply_theme(self.app,prefs.dark)
        except (OSError,ValueError) as exc:
            self.app.dark.set(old.dark)
            self.status.set(str(exc))

    def save_monitoring(self):
        safety=self.app.safety
        try:
            seconds=int(self.interval.get())
            if not 15<=seconds<=3600:
                raise ValueError('Choose a scan interval from 15 to 3600 seconds.')
            prefs=replace(safety.prefs,desktop_interval=seconds,desktop_events=self.events.get())
            save_preferences(prefs)
            safety.prefs=prefs
            if safety.active_root is not None:
                if safety.wakeup is not None:
                    safety.wakeup.close()
                safety.wakeup=Wakeup(safety.active_root,seconds,prefs.desktop_events,event_gap=10)
            self.status.set('Monitoring settings saved.')
        except (OSError,ValueError,RuntimeError) as exc:
            self.status.set(str(exc))


class WelcomeView:
    def __init__(self,app,pages):
        self.app=app
        self.frame=ttk.Frame(pages)
        pages.add(self.frame,text='Getting started')
        self.frame.columnconfigure(0,weight=1)
        ttk.Label(self.frame,text='Welcome to BreakCheck',style='PageTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(self.frame,text=f'v{__version__}  •  Know what breaks before you break it.',style='Muted.TLabel').grid(row=1,column=0,sticky='w',pady=(4,16))
        choices=[('01   Monitor a project','Detect previously observed links that break and review file changes.','Choose project',self.choose),
                 ('02   Explore your storage','See large files, folder sizes and review candidates. Nothing is deleted.','Open Storage',lambda:self.open(app.storage.frame)),
                 ('03   Prepare for recovery','Opt in to local file versions, or manually capture a project.','Open Recovery',lambda:self.open(app.recovery.frame))]
        for i,(title,desc,label,action) in enumerate(choices,2):
            card=ttk.Frame(self.frame,style='Card.TFrame',padding=14)
            card.grid(row=i,column=0,sticky='ew',pady=(0,10))
            ttk.Label(card,text=title,style='Card.TLabel',font=('TkDefaultFont',12,'bold')).pack(anchor='w')
            ttk.Label(card,text=desc,style='CardCaption.TLabel',wraplength=650).pack(anchor='w',pady=(5,8))
            ttk.Button(card,text=label,command=action,style='Accent.TButton' if i==2 else 'TButton').pack(anchor='w')
        ttk.Button(self.frame,text='Continue to overview',command=lambda:self.open(app.safety.frame)).grid(row=5,column=0,sticky='w',pady=8)
        self.status=tk.StringVar(value='No scans, backups or network requests are started by this page.')
        ttk.Label(self.frame,textvariable=self.status,style='Muted.TLabel',wraplength=700).grid(row=6,column=0,sticky='ew')

    def open(self,page):
        try:
            prefs=replace(self.app.safety.prefs,welcome_seen=True)
            save_preferences(prefs)
            self.app.safety.prefs=prefs
        except OSError as exc:
            self.status.set(str(exc))
            return
        self.app.tabs.select(page)

    def choose(self):
        folder=filedialog.askdirectory(parent=self.app)
        if folder:
            if self.app.safety.active_root is not None or self.app.safety.busy:
                self.status.set('Stop monitoring or wait for the current check before choosing another folder.')
                return
            self.app.safety.monitor_path.set(folder)
            self.open(self.app.safety.frame)
            self.app.safety.status.set('Project selected. Click Start monitoring to opt in, or Check now for a single scan.')
