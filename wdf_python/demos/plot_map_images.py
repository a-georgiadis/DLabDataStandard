# Copyright (c) 2023 Renishaw plc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Generate an Raman image from a map section in a Wdf file.
"""

import sys
import os
import argparse
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as tkfiledialog
import tkinter.messagebox as tkmessagebox
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.backends.backend_tkagg as tkagg

# allow demos to load the wdf package from the parent folder (not required for normal installation)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from wdf import (Wdf, WdfBlockId)

if sys.platform == 'win32':
    # Fix for tiny menus on high dpi display
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)


DEF_TITLE = "Wdf Map Demo"


class Plot(ttk.Frame):
    """Embed matplotlib in the Tkinter application window."""
    # ex: https://github.com/I2PC/scipion/blob/master/scipion-master/pyworkflow/matplotlib_image.py
    def __init__(self, master, **kwargs):
        if "figsize" in kwargs:
            self.figsize = kwargs["figsize"]
            del kwargs["figsize"]
        super(Plot, self).__init__(master)
        self.figure = matplotlib.figure.Figure(figsize=self.figsize, frameon=False, dpi=100)
        self.canvas = tkagg.FigureCanvasTkAgg(self.figure, self)
        self.toolbar = None
        widget = self.canvas.get_tk_widget()
        widget.grid(row=0, column=0, sticky=tk.NSEW)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.configure(**kwargs)

    def add_toolbar(self):
        # The next 2 lines are required to ensure the font module actually was loaded
        # to avoid an AttributeError from the NavigationToolbar2Tk class.
        import tkinter.font
        font = tkinter.font.nametofont('TkDefaultFont')
        font.configure(weight=tkinter.font.BOLD)
        self.toolbar = tkagg.NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.master = self.master
        self.toolbar.grid(row=1, column=0, sticky=tk.NSEW)

    def show(self):
        self.canvas.show()

    @property
    def widget(self):
        return self.canvas.get_tk_widget()

    def configure(self, **kwargs):
        return self.widget.configure(**kwargs)


class App(ttk.Frame):
    """Application class."""
    def __init__(self, master, options, **kwargs):
        self.options = options
        super(App, self).__init__(master, **kwargs)
        self.master.wm_minsize(800, 600)
        self.master.wm_title(DEF_TITLE)
        self.create_ui()
        self.create_menu()
        self.grid(row=0, column=0, sticky=tk.NSEW)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

    def create_ui(self):
        upper = ttk.Frame(self)
        label = ttk.Label(upper, text="Maps: ")
        self.maps = ttk.Combobox(upper, values=[], state='readonly')
        self.maps.bind('<<ComboboxSelected>>', self.on_map_select)
        label.grid(row=0, column=0, sticky=tk.NSEW)
        self.maps.grid(row=0, column=1, sticky=tk.NSEW)
        upper.grid_rowconfigure(0, weight=1)
        upper.grid_columnconfigure(1, weight=1)

        self.plot = Plot(self, figsize=(6, 4), background="grey80")

        upper.grid(row=0, column=0, sticky=tk.NSEW)
        self.plot.grid(row=1, column=0, sticky=tk.NSEW)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def create_menu(self):
        menu = tk.Menu(self.master)
        fileMenu = tk.Menu(menu, tearoff=False)
        optMenu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='File', menu=fileMenu)
        menu.add_cascade(label='Options', menu=optMenu)
        fileMenu.add_command(label='Open ...', command=self.on_file_open)
        fileMenu.add_command(label='Exit', command=self.on_file_exit)
        optMenu.add_command(label="Add toolbar", command=self.plot.add_toolbar)
        self.master.configure(menu=menu)

    def on_map_select(self, ev):
        name = self.maps.get()
        section = self._maps[name]
        self.after_idle(self.draw_map, self.options.filename, section.uid)

    def on_file_open(self):
        filetypes = (("WiRE Data Files", "*.wdf"), ("All files", "*.*"))
        filename = tkfiledialog.askopenfilename(filetypes=filetypes)
        if filename:
            self.plot.figure.clear()
            self.options.filename = filename
            self.load(filename)

    def on_file_exit(self):
        self.master.destroy()

    def load(self, filename: str):
        with Wdf(filename) as wdf:
            mapsections = [section for section in wdf.sections() if section.id == WdfBlockId.MAP]
            names = []
            self._maps = {}
            for section in mapsections:
                props = wdf.get_section_properties(section.id, section.uid)
                title = props['Label'].value
                names.append(title)
                self._maps[title] = section
        self.maps.configure(values=names)
        self.after_idle(self.maps.current, 0)
        self.after_idle(self.draw_map, filename, -1)

    def draw_map(self, filename: str, mapindex: int):
        """Reshape the collected data into a numpy array and plot."""
        name = os.path.basename(filename)
        self.master.wm_title(f"{name} - {DEF_TITLE}")

        with Wdf(filename) as wdf:
            shape = wdf.map_area.count.x, wdf.map_area.count.y

            props = wdf.get_section_properties(WdfBlockId.MAP, mapindex)
            title = props['Label'].value
            mapdata = np.array(wdf.get_map_data(mapindex), dtype=float)

            # If the map was aborted early, fill the uncollected range with NaN
            size = shape[0] * shape[1]
            if len(mapdata) != size:
                uncollected = np.full(size - len(mapdata), np.nan, dtype=float)
                mapdata = np.append(mapdata, uncollected, 0)

            fig = self.plot.figure
            fig.clear()
            fig.set_tight_layout(True)

            ax = fig.add_subplot(1, 1, 1)
            ax.set_title(title)
            ax.imshow(mapdata.reshape(shape))

        self.plot.canvas.draw()


def load_idle(root):
    try:
        import idlelib.pyshell as pyshell
        sys.argv = [sys.argv[0], "-n"]
        root.bind("<Control-F2>", lambda ev: pyshell.main())
        root.bind("<Control-i>", lambda ev: pyshell.main())
    except ModuleNotFoundError:
        pass


def main(args=None):
    """Main program entry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename')
    options = parser.parse_args(args)

    global root, app  # access to application for interactive idle mode
    root = tk.Tk()
    app = App(root, options)
    if options.filename:
        app.after_idle(app.load, options.filename)

    root.after_idle(load_idle, root)
    try:
        root.mainloop()
    except Exception as e:
        tkmessagebox.showerror('Error', e)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
