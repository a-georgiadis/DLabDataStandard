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
Browse the structure of a Renishaw WDF file.
"""


import sys
import os
import argparse
import math
import struct
import itertools
import traceback
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog as tkfiledialog
import tkinter.messagebox as tkmessagebox
import tkinter.font as tkfont
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.backends.backend_tkagg as tkagg

from .. import (
    Wdf, WdfBlock, WdfFlags, WdfType, WdfBlockId, WdfStream,
    Pset, PsetType, WdfDataType, WdfDataUnit, WdfScanType, WdfSpectrumFlags)

# Support changes in the Pillow ExifTags API from 9.3.0
import PIL
try:
    from PIL.ExifTags import Base as ExifTagsBase
except ImportError:
    from PIL.ExifTags import TAGS
    from enum import IntEnum
    ExifTagsBase = IntEnum('ExifTagsBase', names=dict((TAGS[t], t) for t in TAGS))


if sys.platform == 'win32':
    # Fix for tiny menus on high dpi display
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)

DEF_TITLE = "Wdf Browser"
WdfBlockIdMap = dict([(getattr(WdfBlockId, name), name)
                      for name in dir(WdfBlockId) if not name.startswith('__')])


class Treeview(ttk.Treeview):
    """Override the default ttk.Treeview class to correct errors in the rowheight
    when used on windows with high-dpi displays."""
    def __init__(self, master, **kwargs):
        if sys.platform == 'win32':
            font = tkfont.nametofont('TkDefaultFont')
            style = ttk.Style(master)
            style.configure('Treeview', rowheight=font.metrics()['linespace'])
        super(Treeview, self).__init__(master, **kwargs)


class Plot(ttk.Frame):
    """Widget to hold the matplotlib plot."""
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
        self.toolbar = tkagg.NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.grid(row=1, column=0, sticky=tk.NSEW)

    def show(self):
        self.canvas.show()

    @property
    def widget(self):
        return self.canvas.get_tk_widget()

    def configure(self, **kwargs):
        return self.widget.configure(**kwargs)


class ImageView(ttk.Frame):
    def __init__(self, master, **kwargs):
        super(ImageView, self).__init__(master, **kwargs)
        self.create()

    def create(self):
        canvas = tk.Canvas(self)
        vs = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        hs = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set, background="white",
                         borderwidth=0, highlightthickness=0)
        canvas.create_image((0, 0), tag="Whitelight", anchor=tk.NW)
        canvas.grid(row=0, column=0, sticky=tk.NSEW)
        vs.grid(row=0, column=1, sticky=tk.NSEW)
        hs.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = canvas

    def set_image(self, image):
        self.image = image
        height = min(image.height(), 480)
        width = min(image.width(), 600)
        scrollregion = (0, 0, image.width(), image.height())
        self.canvas.configure(width=width, height=height, scrollregion=scrollregion)
        self.canvas.itemconfigure("Whitelight", image=self.image)


def CreateScrolledText(parent, **kwargs):
    frame = ttk.Frame(parent)
    text = tk.Text(frame, **kwargs)
    vs = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=vs.set)
    text.grid(row=0, column=0, sticky=tk.NSEW)
    vs.grid(row=0, column=1, sticky=tk.NSEW)
    frame.grid_rowconfigure(0, weight=1)
    frame.grid_columnconfigure(0, weight=1)
    return frame, text


class App(ttk.Frame):
    """Application class"""
    def __init__(self, master, options, **kwargs):
        super(App, self).__init__(master, **kwargs)
        self.options = options
        self.wdf = None
        self.ax = None
        self.master.wm_title(DEF_TITLE)
        self.master.wm_minsize(1152, 800)
        self.create_ui()
        self.create_menu()
        self.grid(row=0, column=0, sticky=tk.NSEW)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        if options.filename:
            self.after_idle(self.load, options.filename)

    def create_ui(self):
        self.font = tkfont.nametofont('TkDefaultFont')
        self.bold = tkfont.Font(**dict(self.font.actual(), weight=tkfont.BOLD), root=self.master)
        self.pw = ttk.Panedwindow(self, orient=tk.HORIZONTAL)

        treeframe = ttk.Frame(self.pw)
        self.tree = Treeview(treeframe)
        tvs = ttk.Scrollbar(treeframe, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tvs.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        tvs.grid(row=0, column=1, sticky=tk.NSEW)
        treeframe.grid_rowconfigure(0, weight=1)
        treeframe.grid_columnconfigure(0, weight=1)
        self.tree.configure(columns=('value'))
        self.tree.column("value", anchor=tk.W)
        self.tree.heading("value", anchor=tk.W, text="Value")

        self.notebook = ttk.Notebook(self.pw)

        self.spectrumIndex = tk.IntVar(self, value=0)
        plotframe = ttk.Frame(self.notebook)
        textframe, self.info = CreateScrolledText(
            plotframe, height=6, state="disabled", font=self.font)
        self.info.tag_configure("heading", font=self.bold)
        textframe.grid(row=0, column=0, sticky=tk.NSEW)
        plotbox = ttk.Frame(plotframe)
        label = ttk.Label(plotbox, text="Spectrum: ")
        label.pack(side=tk.LEFT)
        self.slider = ttk.Scale(plotbox, from_=0, to=100, command=self.update_plot)
        self.slider.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.spinbox = ttk.Spinbox(plotbox, textvariable=self.spectrumIndex,
                                   width=8, command=self.update_plot)
        self.spinbox.pack(side=tk.RIGHT)
        self.plot = Plot(plotframe, figsize=(11, 8), background="grey80")
        self.plot.grid(row=1, column=0, sticky=tk.NSEW)
        plotbox.grid(row=2, column=0, sticky=tk.NSEW)
        plotframe.grid_rowconfigure(1, weight=1)
        plotframe.grid_columnconfigure(0, weight=1)

        self.imageview = ImageView(self.notebook)

        self.notebook.add(plotframe, text="Spectral data")
        self.notebook.add(self.imageview, text="Image", state=tk.HIDDEN)

        self.pw.add(treeframe, weight=1)
        self.pw.add(self.notebook, weight=1)
        self.pw.grid(row=0, column=0, sticky=tk.NSEW)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def create_menu(self):
        menu = tk.Menu(self.master)
        fileMenu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label='File', menu=fileMenu)
        fileMenu.add_command(label='Open ...', command=self.on_file_open)
        fileMenu.add_command(label='Exit', command=self.on_file_exit)
        self.master.configure(menu=menu)

    def on_file_exit(self):
        self.master.destroy()

    def on_file_open(self):
        filetypes = (('WiRE Data Files', '*.wdf'), ('All files', '*.*'))
        filename = tkfiledialog.askopenfilename(filetypes=filetypes)
        if filename:
            self.options.filename = filename
            self.after_idle(self.load, filename)

    def update_plot(self, spectrumIndex: str = None):
        if not spectrumIndex:
            index = self.spectrumIndex.get()
            self.slider.set(index)
        else:
            index = int(float(spectrumIndex))
            self.spectrumIndex.set(index)
        if self.wdf:
            if not self.ax:
                self.ax = self.create_ax()
            if self.wdf.hdr.ylistcount > 1:
                self.update_image_plot(index)
            else:
                self.update_spectrum_plot(index)

    def create_ax(self):
        fig = self.plot.figure
        fig.set_tight_layout(True)
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title(self.wdf.hdr.title)
        return ax

    def update_spectrum_plot(self, index):
        track = 0
        if (self.wdf.hdr.flags & WdfFlags.Multitrack
                and self.wdf.hdr.ntracks == self.wdf.hdr.nspectra):
            track = index
        self.ax.clear()
        self.ax.plot(self.wdf.xlist(track), self.wdf[index])
        self.plot.canvas.draw()

    def update_image_plot(self, index):
        shape = self.wdf.hdr.ylistcount, self.wdf.hdr.xlistcount
        data = np.array(self.wdf[index], dtype=float)
        data = np.flipud(np.fliplr(data.reshape(shape)))
        self.ax.clear()
        self.ax.imshow(data)
        self.plot.canvas.draw()

    def update_info(self):
        self.info.configure(state="normal")
        self.info.delete("0.0", "end")
        summary = ""
        if self.wdf.hdr.ylistcount > 1:
            summary += f"Spectral image {self.wdf.hdr.ylistcount} by {self.wdf.hdr.xlistcount}"
        else:
            spectra = "spectrum" if self.wdf.hdr.ncollected == 1 else "spectra"
            summary += f"{self.wdf.hdr.ncollected} {spectra} of {self.wdf.hdr.npoints} points"
        if self.wdf.hdr.ntracks > 1:
            summary += f" with {self.wdf.hdr.ntracks} tracks"
        self.info.insert(
            tk.END, self.wdf.hdr.title, "", "\n", "",
            summary, "", "\n", "",
            "Description:", "heading", "\n", "",
            self.wdf.comment(), "", "\n", "")
        self.info.configure(state="disabled")

    def load(self, filename):
        name = os.path.basename(filename)
        self.master.wm_title(f"{name} - {DEF_TITLE}")
        self.tree.delete(*self.tree.get_children())
        self.wdf = Wdf(filename)
        self.spinbox.configure(from_=0, to=self.wdf.hdr.ncollected - 1)
        self.spectrumIndex.set(0)
        self.slider.configure(to=self.wdf.hdr.ncollected - 1)
        self.update_plot(0)
        self.update_info()
        self.notebook.tab(self.imageview, state=tk.HIDDEN)
        for section in self.wdf.sections():
            name = WdfBlockIdMap[section.id]
            uid = f" {section.uid}" if section.uid > 0 else ""
            item = self.tree.insert("", tk.END, None, text=f"{name}{uid}")
            # Call custom load methods if defined (for sections without a pset)
            if hasattr(self, f"load_{name}"):
                getattr(self, f"load_{name}")(self.wdf, item, section)
            else:
                self.load_section(self.wdf, item, section)
            # call custom post-load methods if defined
            if hasattr(self, f"postload_{name}"):
                getattr(self, f"postload_{name}")(item, section)
            extra = section.size - (self.wdf.fd.tell() - section.position)
            if extra > 0:
                self.tree.insert(item, tk.END, None, text="_extra", values=(extra,))

    def load_FILE(self, wdf: Wdf, parent: str, section: WdfBlock):
        self.tree.item(parent, text="header")
        for field in ("appname", "appversion", "flags", "laser_wavenumber", "naccum", "nspectra",
                      "npoints", "ncollected", "ntracks", "units", "status", "uuid",
                      "time_start", "time_end", "scantype", "origincount", "type",
                      "xlistcount", "ylistcount", "user", "title"):
            if field == "flags":
                value = ", ".join([flag.name for flag in WdfFlags if flag.value & wdf.hdr.flags])
            elif field == "units":
                value = WdfDataUnit(wdf.hdr.units).name
            elif field == "type":
                value = WdfType(wdf.hdr.type).name
            elif field == "scantype":
                value = WdfScanType(wdf.hdr.scantype).name
            else:
                value = getattr(wdf.hdr, field)
            self.tree.insert(parent, tk.END, None, text=field, values=(value,))

    def load_DATA(self, wdf: Wdf, parent: str, section: WdfBlock):
        text = f"{wdf.hdr.ncollected} spectra of {wdf.hdr.npoints} points"
        self.tree.item(parent, values=(text,))

    def load_XLIST(self, wdf: Wdf, parent: str, section: WdfBlock, countfield="xlistcount"):
        wdf.fd.seek(int(section.position) + 16, 0)
        datatype, dataunit, = struct.unpack('<II', wdf.fd.read(8))
        datatype = WdfDataType(datatype)
        dataunit = WdfDataUnit(dataunit)
        count = getattr(wdf.hdr, countfield)
        wdf.fd.seek(count * 4, os.SEEK_CUR)  # skip over the data
        prefix = ""
        if section.id == WdfBlockId.XLIST and wdf.hdr.ntracks > 0:
            prefix = f"{wdf.hdr.ntracks} tracks of "
            wdf.fd.seek(
                section.position + WdfBlock._SIZE + 8
                + (4 * wdf.hdr.ntracks * wdf.hdr.npoints), os.SEEK_SET)
        label = "values" if count > 1 else "value"
        text = f"{prefix}{count} {label} ({dataunit.name})"
        self.tree.item(parent, values=(text,))
        self.tree.insert(parent, tk.END, None, text="type", values=(datatype.name,))
        self.tree.insert(parent, tk.END, None, text="units", values=(dataunit.name,))

    def load_BKXLIST(self, wdf: Wdf, parent: str, section: WdfBlock):
        self.load_XLIST(wdf, parent, section)

    def load_YLIST(self, wdf: Wdf, parent: str, section: WdfBlock):
        self.load_XLIST(wdf, parent, section, countfield="ylistcount")

    def load_COMMENT(self, wdf: Wdf, parent: str, section: WdfBlock):
        text = wdf.comment()
        if len(text) > 30:
            text = text[:30] + "..."
        self.tree.insert(parent, tk.END, None, text=text)

    def load_CHECKSUM(self, wdf: Wdf, parent: str, section: WdfBlock):
        stream = wdf.get_section_stream(section.id, section.uid)
        count = struct.unpack('<I', stream.read(4))[0]
        for _ in range(count):
            id, uid, digest = struct.unpack('<II20s', stream.read(28))
            name = WdfBlockIdMap[id]
            uid = f" {uid}" if uid > 0 else ""
            digest = "".join([f"{b:02x}" for b in digest])
            self.tree.insert(parent, tk.END, None, text=f"{name}{uid}", values=(digest,))

    def load_MAPAREA(self, wdf: Wdf, parent: str, section: WdfBlock):
        maparea = wdf.map_area
        self.tree.insert(parent, tk.END, None, text="flags", values=(maparea.flags.name,))
        self.tree.insert(parent, tk.END, None, text="lfcount", values=(maparea.lfcount,))
        self.insert_vector(parent, "Position", maparea.start)
        self.insert_vector(parent, "Step size", maparea.step)
        self.insert_vector(parent, "Count", maparea.count)

    def load_ORIGIN(self, wdf: Wdf, parent: str, section: WdfBlock):
        for key in wdf.origins:
            origin = wdf.origins[key]
            node = self.tree.insert(parent, tk.END, None, text=origin.label)
            self.tree.insert(node, tk.END, None, text="type", values=(origin.datatype.name,))
            self.tree.insert(node, tk.END, None, text="units", values=(origin.dataunit.name,))
            self.tree.insert(node, tk.END, None, text="alternate", values=(not origin.is_primary,))
            if key == WdfDataType.Checksum:
                data = []
                for digest in [struct.pack('<Q', v) for v in origin[:10]]:
                    data.append("".join([f"{b:02x}" for b in digest]))
            elif key == WdfDataType.Flags:
                data = []
                filtered = (
                    v for v in itertools.filterfalse(lambda x: x[1] == 0,
                                                     zip(itertools.count(), origin)))
                for index, value in itertools.islice(filtered, 10):
                    s = ",".join([f"{index}:{flag.name}" for flag in WdfSpectrumFlags if flag.value & value])
                    data.append(s)
            else:
                data = [str(v) for v in origin[:10]]
            data = " ".join(data)
            if len(origin) > 1:
                data += "..."
            self.tree.insert(node, tk.END, None, text="data", values=(data,))

    def load_WHITELIGHT(self, wdf: Wdf, parent: str, section: WdfBlock):
        stream = wdf.get_section_stream(section.id, section.uid)
        image = PIL.Image.open(stream)
        self.imageview.set_image(PIL.ImageTk.PhotoImage(image=image))
        self.notebook.tab(self.imageview, state=tk.NORMAL)
        exif = image.getexif()
        for tag in exif:
            try:
                if tag == 0xfea0:
                    name = "Position"
                    value = str(exif[tag])
                elif tag == 0xfea1:
                    name = "Field of view (1x)"
                    value = str(exif[tag])
                elif tag == 0xfea2:
                    name = "Objective"
                    value = str(exif[tag])
                else:
                    name = ExifTagsBase(tag).name
                    value = exif[tag]
                    if tag == ExifTagsBase.ImageDescription:
                        self.tree.item(parent, values=(value,))
            except ValueError:
                name = f"{tag:#04x}"
                value = exif[tag]
            self.tree.insert(parent, tk.END, None, text=name, values=(value,))

    def load_DATASETDATA(self, wdf: Wdf, parent: str, section: WdfBlock):
        self.tree.item(parent, values=("Per-dataset values",))
        stream = wdf.get_section_stream(section.id, section.uid)
        count, index = 0, 0
        while count < 10 and index < wdf.hdr.ncollected:
            stream.seek(8 * count)
            offset = struct.unpack('<Q', stream.read(8))[0]
            if offset != 0:
                stream.seek(offset - WdfBlock._SIZE)
                length = struct.unpack('<I', stream.read(4))[0]
                pset = Pset.fromstream(stream, None, length)
                node = self.tree.insert(parent, tk.END, None, text=f"{index}")
                self.tree_insert(node, pset)
                count += 1
            index += 1
        if index < wdf.hdr.ncollected:
            self.tree.insert(parent, tk.END, None, text='...')

    def insert_vector(self, parent: str, name: str, vector):
        node = self.tree.insert(parent, tk.END, None, text=name)
        for axis in ('x', 'y', 'z'):
            self.tree.insert(node, tk.END, None, text=axis,
                             values=(getattr(vector, axis),))

    def load_section(self, wdf: Wdf, parent: str, section: WdfBlock):
        try:
            props = wdf.get_section_properties(section.id, section.uid)
            if props:
                self.tree_insert(parent, props)
        except Exception as e:
            print(f"error {WdfBlockIdMap[section.id]}: {e}")
            traceback.print_exc(file=sys.stdout)

    def tree_insert(self, parent: str, pset: Pset):
        if pset:
            if "Label" in pset.items:
                self.tree.item(parent, values=(pset["Label"].value,))
            ndx = 0
            for key, item in pset:
                if item.type == PsetType.Pset:
                    node = self.tree.insert(parent, tk.END, f"{parent}:{ndx}", text=key, values=())
                    self.tree_insert(node, item.value)
                else:
                    count = 1
                    if item.type == PsetType.String:
                        count = len(item.value.splitlines())
                    if count > 1:
                        value = f"[ {count} lines ]"
                    else:
                        value = item.value
                    self.tree.insert(parent, tk.END, f"{parent}:{ndx}", text=key, values=(value,))
                ndx += 1

    def postload_WIREDATA(self, parent: str, section: WdfBlock):
        self.tree.item(parent, text="properties")

    def postload_MAP(self, parent: str, section: WdfBlock):
        data = self.wdf.get_map_data(section.uid)
        value = f"({data.count}) "
        value += " ".join([f"{v:.3f}" for v in data[:10]])
        self.tree.insert(parent, tk.END, None, text="data", values=(value,))
        self.wdf.fd.seek(section.position + (8 * len(data)), os.SEEK_SET)

    def postload_CURVEFIT(self, parent: str, section: WdfBlock):
        props = self.wdf.get_section_properties(section.id, section.uid)
        stream = self.wdf.get_section_stream(section.id, section.uid)
        _ = struct.unpack('<I', stream.read(4))[0]  # unused
        ncurves = props.items['CurveCount'].value
        node = self.tree.insert(parent, tk.END, None, text="Results",
                                values=(f"{ncurves} curves",))
        fmt = "4f" * ncurves + "2f"
        for index in range(min(self.wdf.hdr.nspectra, 10)):  # show results for up to 10 spectra
            result = struct.unpack(fmt, stream.read(4 * ((4 * ncurves) + 2)))
            value = " ".join([f"{v:.3f}" for v in result])
            self.tree.insert(node, tk.END, None, text=str(index), values=(value,))
        if self.wdf.hdr.nspectra > 10:
            self.tree.insert(node, tk.END, None, text="...")
        datasize = 4 + (self.wdf.hdr.nspectra * (4 * ((4 * ncurves) + 2)))
        self.wdf.fd.seek(stream.section.position + datasize, os.SEEK_SET)


def load_pyshell(root):
    """Load the IDLE shell and bind to Ctrl-F2 and/or Ctrl-i
    The app object instance and the Tk root window are exposed to the shell."""
    try:
        import idlelib.pyshell as pyshell

        def pyshell_run(ev):
            """Launch the IDLE shell and expose our app instance to the interactive shell"""
            flist = pyshell.PyShellFileList(root)
            shell = flist.open_shell(ev)
            shell.interp.runcode('from wdf.browser import root, app')

        sys.argv = [sys.argv[0], '-n']
        root.bind("<Control-F2>", pyshell_run)
        root.bind("<Control-i>", pyshell_run)
    except ModuleNotFoundError:
        pass


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('filename', nargs='?', help="Path to the Wdf file.")
    options = parser.parse_args(args)

    global root, app
    root = tk.Tk()
    app = App(root, options)
    root.after_idle(load_pyshell, root)
    try:
        root.mainloop()
    except Exception as e:
        tkmessagebox.showerror('Error', e)
    return 0
