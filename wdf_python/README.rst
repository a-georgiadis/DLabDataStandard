=========================
Renishaw Wdf File Support
=========================

This package provides Python support for using Renishaw Wdf data files. These
files are used to hold spectroscopic data from the line of
`Raman microscopes <https://www.renishaw.com/en/raman-products--25893>`_
manufactured by `Renishaw plc <https://renishaw.com/>`_.

This package requires Python 3.8 or later.

See the accompanying file *LICENSE* for license details.


Documentation
=============

The package is documented using python docstrings which yield assistance in most editors.
Documentation can be generated using ``pydoc``:

.. code-block:: console

    $ python -m pydoc *Entity name*

For instance:

.. code-block:: console

    $ python -m pydoc wdf.Wdf

Basic usage
===========

Use the Wdf class to open data files.
For instance, to print the values for the first spectrum in a file to two columns:

.. code-block:: python

    from wdf import Wdf
    with Wdf(filename) as data:
        for x, i in zip(data.xlist(), data[0]):
            print(f"{x}\t{i}")

Or using matplotlib to plot the spectral data graphically:

.. code-block:: python

    import matplotlib.pyplot as plt
    from wdf import Wdf
    with Wdf(filename) as data:
        plt.plot(data.xlist(), data[0])
        plt.show()

The Wdf class is iterable and supports indexing to obtain spectra. The result of ``Wdf[]``
or ``Wdf.spectrum()`` is a non-mutable sequence of floating point values.

A Wdf file is divided into sections, many of which store a collection of named properties.
Known section identifiers are provided by constants in the WdfBlockId module and sections are
identified by an ID (defining a type of section) and a unique ID (defining a specific instance).
To obtain the properties for a the first map section stored in a file the ``get_section_properties``
method can be used as shown below.

.. code-block:: python

    from wdf import WdfBlockId
    props = data.get_section_properties(WdfBlockId.MAP, -1)
    print(props["Title"].value)

Spectra often have additional information stored about the collection environment such as
the time collected or the X and Y position of the spectrum if part of an area map, or the
temperature for a member of a temperature series. These values are stored as data origins
and are accessed using the ``origins`` property with the data type as a key to obtain the
sequence of values that can then be indexed by the spectrum index.

.. code-block:: python

    from wdf import Wdf, WdfDataType
    index = 1  # spectrum index
    with Wdf(filename) as data:
        # the spectrum timestamp (as a datetime)
        timestamp = data.origins[WdfDataType.Time][index]
        # Print all data origin values:
        for origin in data.origins:
            print(origin, data.origins[origin][index], sep="\t")

Map information
===============

If the file contains maps generated from the collected data these can be plotted
using numpy and matplotlib.

.. code-block:: python

    import numpy as np
    import matplotlib.pyplot as plt
    from wdf import Wdf, WdfBlockId
    mapindex = -1  # first available map
    with Wdf(filename) as data:
        shape = data.map_area.count.x, data.map_area.count.y
        mapinfo = data.get_section_properties(WdfBlockId.MAP, mapindex)
        mapdata = np.array(data.get_map_data(mapindex), dtype=float)

        fig = plt.figure()
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title(mapinfo["Label"].value)
        ax.imshow(mapdata.reshape(shape))
        fig.show()

Example files
=============

There are some examples of using the library in the ``demos/`` folder.

The installation will also register *wdfbrowser* as an executable application. This is
implemented from the ``wdf.browser`` module and provides a view of all the sections and
properties provided in a Wdf file.

The *wdfbrowser* utility depends on additional packages: numpy, matplotlib and Pillow.
These can be installed using ``pip`` or any other package management tool.

.. code-block:: console

    $ pip install numpy matplotlib Pillow

The *wdf* package does not have any package dependencies beyond the python standard library.

Installation from source
========================

.. code-block:: console

    $ python setup.py install

Bugs and issues
===============

Bug reports should be e-mailed to the support contact for the package.
