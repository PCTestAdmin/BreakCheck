"""Tk views for the dependency graph, asset inventory and light/dark theme."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from .insights import candidates, impact_graph, NOTICE


def relative(path, root):
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def shorten(text, limit=32):
    return text if len(text) <= limit else '…' + text[-(limit - 1):]


class InsightsView:
    def __init__(self, tabs):
        self.report = None
        self.dark = False
        graph = ttk.Frame(tabs, padding=8)
        tabs.add(graph, text='Dependency graph')
        graph.columnconfigure(0, weight=1)
        graph.rowconfigure(2, weight=1)
        ttk.Label(graph, text='Dependency graph', style='PageTitle.TLabel').grid(row=0,column=0,sticky='w',pady=(0,10))
        self.graph_status = ttk.Label(graph, text='Analyze a target to visualize observed references.')
        self.graph_status.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        self.canvas = tk.Canvas(graph, highlightthickness=0)
        self.canvas.grid(row=2, column=0, sticky='nsew')
        ybar = ttk.Scrollbar(graph, command=self.canvas.yview)
        ybar.grid(row=2, column=1, sticky='ns')
        xbar = ttk.Scrollbar(graph, orient='horizontal', command=self.canvas.xview)
        xbar.grid(row=3, column=0, sticky='ew')
        self.canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.canvas.bind('<ButtonPress-2>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B2-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.selected = ttk.Label(graph, text='Select a node to inspect its path.', wraplength=850)
        self.selected.grid(row=4, column=0, columnspan=2, sticky='w', pady=5)

        assets = ttk.Frame(tabs, padding=8)
        tabs.add(assets, text='Unreferenced assets')
        assets.columnconfigure(0, weight=1)
        assets.rowconfigure(3, weight=1)
        ttk.Label(assets, text='Unreferenced assets', style='PageTitle.TLabel').grid(row=0,column=0,sticky='w',pady=(0,10))
        ttk.Label(assets, text=NOTICE, wraplength=730).grid(row=1, column=0, columnspan=2, sticky='w')
        self.asset_status = ttk.Label(assets, text='No scan performed.')
        self.asset_status.grid(row=2, column=0, columnspan=2, sticky='w', pady=5)
        self.assets = ttk.Treeview(assets, columns=('path', 'size'), show='headings')
        self.assets.heading('path', text='Media asset — review manually')
        self.assets.heading('size', text='Size (bytes)')
        self.assets.column('path', width=640)
        self.assets.column('size', width=130, anchor='e', stretch=False)
        self.assets.grid(row=3, column=0, sticky='nsew')
        bar = ttk.Scrollbar(assets, command=self.assets.yview)
        bar.grid(row=3, column=1, sticky='ns')
        self.assets.configure(yscrollcommand=bar.set)

    def clear(self):
        self.report = None
        self.canvas.delete('all')
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.graph_status.configure(text='Analyze a target to visualize observed references.')
        self.selected.configure(text='Select a node to inspect its path.')
        self.assets.delete(*self.assets.get_children())
        self.asset_status.configure(text='No scan performed.')

    def render(self, report):
        self.clear()
        self.report = report
        rows = candidates(report.scan)
        total = sum(size for _, size in rows)
        self.asset_status.configure(text=f'{len(rows):,} candidate assets • {total / 1048576:,.2f} MiB • showing up to 1,000 • not a deletion recommendation')
        for path, size in rows[:1000]:
            self.assets.insert('', 'end', values=(relative(path, report.scan.root), f'{size:,}'))
        self.draw()

    def draw(self):
        bg = '#111827' if self.dark else '#f8fafc'
        fg = '#e5e7eb' if self.dark else '#111827'
        self.canvas.configure(background=bg)
        self.canvas.delete('all')
        if self.report is None:
            return
        roles, edges, omitted = impact_graph(self.report)
        self.graph_status.configure(text=f'{len(roles)} nodes • {len(edges)} observed links • red = predicted break • {omitted} links omitted by display limits')
        columns = ('Indirect', 'Direct', 'Referenced', 'Target')
        colors = {'Indirect': '#64748b', 'Direct': '#b45309', 'Referenced': '#475569', 'Target': '#2563eb'}
        positions = {}
        for col, role in enumerate(columns):
            x = 32 + col * 250
            self.canvas.create_text(x + 105, 24, text=role.upper(), fill=fg, font=('TkDefaultFont', 10, 'bold'))
            group = sorted((p for p, r in roles.items() if r == role), key=str)
            for row, path in enumerate(group):
                positions[path] = (x, 48 + row * 66)
        for source, target, broken in edges:
            sx, sy = positions[source]
            tx, ty = positions[target]
            color = '#ef4444' if broken else '#94a3b8'
            if source == target:
                points = (sx + 210, sy + 12, sx + 232, sy + 12, sx + 232, sy + 38, sx + 210, sy + 38)
            elif sx == tx:
                points = (sx + 210, sy + 22, sx + 230, sy + 22, tx + 230, ty + 22, tx + 210, ty + 22)
            elif sx < tx:
                points = (sx + 210, sy + 22, tx, ty + 22)
            else:
                points = (sx, sy + 22, tx + 210, ty + 22)
            self.canvas.create_line(*points, fill=color, width=2 if broken else 1, arrow='last')
        for i, (path, (x, y)) in enumerate(positions.items()):
            role = roles[path]
            label = relative(path, self.report.scan.root)
            tag = f'node{i}'
            self.canvas.create_rectangle(x, y, x + 210, y + 44, fill=colors[role], outline='', tags=(tag,))
            self.canvas.create_text(x + 105, y + 22, text=shorten(label), fill='#ffffff', tags=(tag,))
            self.canvas.tag_bind(tag, '<Button-1>', lambda _, p=path, r=role: self.selected.configure(text=f'{r}: {p}'))
        height = max(y for _, y in positions.values()) + 70
        self.canvas.configure(scrollregion=(0, 0, 1010, height))


def apply_theme(app, dark):
    style = ttk.Style(app)
    style.theme_use('clam')
    if dark:
        bg, panel, sidebar, fg, muted, border, accent, hover = ('#111827','#1c2636','#101621','#edf2f7','#a5b4c7','#344258','#2563eb','#29374c')
    else:
        bg, panel, sidebar, fg, muted, border, accent, hover = ('#f0f3f8','#ffffff','#e2e8f0','#172338','#526277','#cbd5e1','#215fcf','#dbe5f4')
    header = sidebar
    font = 'Segoe UI' if __import__('os').name == 'nt' else 'TkDefaultFont'
    app.configure(background=bg)
    style.configure('.', background=bg, foreground=fg, font=(font, 10), bordercolor=border,
                    lightcolor=border, darkcolor=border, focuscolor=accent, fieldbackground=panel)
    style.configure('TFrame', background=bg)
    style.configure('TLabel', background=bg, foreground=fg)
    style.configure('PageTitle.TLabel', font=(font, 23, 'bold'))
    style.configure('Section.TLabel', font=(font, 12, 'bold'))
    style.configure('Muted.TLabel', foreground=muted)
    style.configure('Card.TFrame', background=panel)
    style.configure('Card.TLabel', background=panel, foreground=fg)
    style.configure('CardCaption.TLabel', background=panel, foreground=muted, font=(font, 10))
    style.configure('Metric.TLabel', background=panel, foreground=fg, font=(font, 24, 'bold'))
    style.configure('Header.TFrame', background=header)
    style.configure('Brand.TLabel', background=header, foreground=fg, font=(font, 18, 'bold'))
    style.configure('HeaderCaption.TLabel', background=header, foreground=muted, font=(font, 9))
    style.configure('Sidebar.TFrame', background=sidebar)
    style.configure('SidebarCaption.TLabel', background=sidebar, foreground=muted, font=(font, 9, 'bold'))
    style.configure('TButton', padding=(12,8), borderwidth=1, relief='flat', background=panel,
                    foreground=fg, bordercolor=border, lightcolor=panel, darkcolor=panel)
    style.map('TButton', background=[('disabled', bg), ('active', hover), ('pressed', hover)],
              foreground=[('disabled', muted)])
    style.configure('Accent.TButton', background=accent, foreground='#ffffff', bordercolor=accent,
                    lightcolor=accent, darkcolor=accent)
    style.map('Accent.TButton', background=[('disabled', bg), ('active', '#1d4ed8'), ('pressed', '#1e40af')],
              foreground=[('disabled', muted), ('!disabled', '#ffffff')])
    for name, color in [('Nav.TButton', sidebar), ('SelectedNav.TButton', hover)]:
        style.configure(name, anchor='w', padding=(12,8), width=18, borderwidth=0,
                        background=color, foreground=fg, lightcolor=color, darkcolor=color, bordercolor=color)
        style.map(name, background=[('active', hover), ('!active', color)])
    style.configure('TEntry', padding=7, fieldbackground=panel, foreground=fg, insertcolor=fg, borderwidth=1)
    style.map('TEntry', fieldbackground=[('disabled', bg)], foreground=[('disabled', muted)])
    style.configure('TCombobox', padding=6, fieldbackground=panel, background=panel, foreground=fg,
                    arrowcolor=fg, arrowsize=15)
    style.map('TCombobox', fieldbackground=[('readonly', panel)], foreground=[('readonly', fg)])
    style.configure('TCheckbutton', background=bg, foreground=fg, padding=3, indicatorcolor=panel)
    style.configure('Header.TCheckbutton', background=header, foreground=fg)
    style.map('TCheckbutton', indicatorcolor=[('selected', accent), ('!selected', panel)], background=[('active', bg)])
    style.map('Header.TCheckbutton', background=[('active', header)])
    style.configure('TNotebook', background=bg, borderwidth=0, tabmargins=(0,0,0,8))
    style.configure('TNotebook.Tab', background=bg, foreground=muted, padding=(14,9), borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', panel), ('active', hover)], foreground=[('selected', fg)])
    style.configure('Treeview', rowheight=30, fieldbackground=panel, background=panel,
                    foreground=fg, borderwidth=0, relief='flat')
    style.configure('Treeview.Heading', background=hover, foreground=fg, padding=8,
                    font=(font, 10, 'bold'), relief='flat')
    style.map('Treeview', background=[('selected', accent)], foreground=[('selected', '#ffffff')])
    style.map('Treeview.Heading', background=[('active', border)])
    for axis in ('Vertical', 'Horizontal'):
        style.configure(f'{axis}.TScrollbar', background=border, troughcolor=bg, arrowcolor=muted,
                        bordercolor=bg, lightcolor=border, darkcolor=border, arrowsize=13)
    app.coverage.configure(background=panel, foreground=fg, insertbackground=fg, relief='flat', borderwidth=0)
    if hasattr(app, 'repair'):
        app.repair.diff.configure(background=panel, foreground=fg, insertbackground=fg, relief='flat', borderwidth=0)
    if hasattr(app, 'storage'):
        app.storage.draw()
    if hasattr(app, 'guard'):
        app.guard.text.configure(background=panel,foreground=fg,insertbackground=fg,relief='flat',borderwidth=0)
    app.insights.dark = dark
    app.insights.draw()
