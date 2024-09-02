Installation
==================================

.. _installation:

.. attention::

   `geeViz` uses Google Earth Engine (GEE) for much of its functionality. It requires an active Earth Engine account and associated Google Cloud Platform project ID.
   If you have not signed up for GEE, please sign up `here. <https://code.earthengine.google.com/register>`_


Installing `geeViz`
-----------------------------------------
`geeViz` will try to automatically install the `earthengine-api` package, but sometimes this fails for various reasons. In this instance refer to `this <https://developers.google.com/earth-engine/guides/python_install>`_ to troubleshoot.


You can also manually install the package:

.. code-block:: console

   $ pip install earthengine-api



Then, install `geeViz` using pip:

.. code-block:: console

   $ pip install geeViz

While `geeViz` will try to authenticate and initialize GEE, it does fail to figure out the multitude of builds and authentication methods. This process changes frequently. Following the directions `here <https://developers.google.com/earth-engine/guides/python_install>`_ can be the best approach.

While many examples in `geeViz` do not initialize to a project in the example's code, we recommend you follow the best practice of initializing GEE to a project prior to importing any `geeViz` modules: 
   .. code-block:: python

      import ee 
      ee.Initialize(project='someProject')
      import geeViz.geeView as gv 
      Map = gv.Map
      Map.addLayer(someEEImage,{},'Some Image')
      Map.view()
      



Getting Started
-----------------------------------------
Check out the :doc:`examples` for use case example scripts and notebooks.

Check out the :doc:`modules` for code documentation.

