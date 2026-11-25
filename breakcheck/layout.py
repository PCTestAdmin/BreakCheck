"""Desktop workspace navigation with accessible native controls."""
from tkinter import ttk


class Pages(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = ttk.Frame(self, style='Sidebar.TFrame', padding=(14, 22))
        self.sidebar.grid(row=0, column=0, sticky='ns')
        self.sidebar.configure(width=205)
        self.nav = ttk.Frame(self.sidebar, style='Sidebar.TFrame')
        ttk.Label(self.sidebar, text='WORKSPACE', style='SidebarCaption.TLabel').pack(anchor='w', padx=10, pady=(0,12))
        self.nav.pack(fill='x')
        ttk.Label(self.sidebar, text='LOCAL  /  PRIVATE', style='SidebarCaption.TLabel').pack(side='bottom', anchor='w', padx=10, pady=8)
        self.pages = []
        self.buttons = {}
        self.labels = {}
        self.current = None

    def add(self, child, text=''):
        self.insert(len(self.pages), child, text=text)

    def insert(self, index, child, text=''):
        self.pages.insert(index, child)
        self.labels[child] = text
        self.buttons[child] = ttk.Button(self.nav, text=text, style='Nav.TButton',
                                         command=lambda page=child: self.select(page))
        for page in self.pages:
            self.buttons[page].pack_forget()
        for page in self.pages:
            self.buttons[page].pack(fill='x', pady=2)
        if self.current is None:
            self.select(child)

    def select(self, child=None):
        if child is None:
            return str(self.current) if self.current is not None else ''
        if child not in self.pages:
            raise ValueError('Unknown workspace page')
        if self.current is not None:
            self.current.grid_remove()
            self.buttons[self.current].configure(style='Nav.TButton')
        self.current = child
        child.grid(row=0, column=1, sticky='nsew', padx=22, pady=18)
        self.buttons[child].configure(style='SelectedNav.TButton')

    def tab(self, child, **kwargs):
        if 'text' in kwargs:
            self.labels[child] = kwargs['text']
            self.buttons[child].configure(text=kwargs['text'])
