Stpl2
=====

.. image:: https://travis-ci.org/ergoithz/stpl2.png?branch=master
  :target: https://travis-ci.org/ergoithz/stpl2
  :alt: Build status

.. image:: https://coveralls.io/repos/ergoithz/stpl2/badge.png
  :target: https://coveralls.io/r/ergoithz/stpl2
  :alt: Test coverage

.. image:: https://pypip.in/version/stpl2/badge.png
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: Latest Version

.. image:: https://pypip.in/egg/stpl2/badge.png
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: Egg Status

.. image:: https://pypip.in/wheel/stpl2/badge.png
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: Wheel Status

.. image:: https://pypip.in/license/stpl2/badge.png
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: License

Stpl2 is a compatible reimplementation of bottle-py's SimpleTemplate Engine.

Install
=======

Stpl2 is under active development but can be considered production-ready.


Stable releases are available on PyPI.

.. code-block:: bash

    pip install stpl2

Or, if you're brave enough for using the in-development code, you can download straight from github.

.. code-block:: bash

    pip install https://github.com/ergoithz/stpl2.git

Overview
========

This project aims full compatibility with `bottle.py` `SimpleTemplate Engine` template syntax, and started as a replacement for streaming templates using **yield**.

.. _bottle.py: https://github.com/defnull/bottle
.. _SimpleTemplate Engine: http://bottlepy.org/docs/dev/stpl.html

Simple
------

Stpl2 is very simple, templates are parsed line by line, yielding readable high quality python code you can find on `Template`.`pycode` instance attribute, and then compiled, cached and wrapped on-demand into `TemplateContext` which cares about template inheritance, rebasing, updating variables and so on.

template.tpl

::

    % # my simple template
    Literal line
    {{ myvar }}
    % for i in range(100):
      {{ ! i }}
    % end

Generated python code

.. code-block:: python

    # -*- coding: UTF-8 -*-
    def __template__():
        # my simple template                                #lineno:1#
        yield (                                             #lineno:2#
            'Literal line\n'
            '%s\n'                                          #lineno:3#
            ) % (_escape(myvar),)                           #lineno:4#
        for i in range(100):
            yield (                                         #lineno:5#
                '  %s\n'
                ) % (i,)                                    #lineno:6#
    __blocks__ = {}
    __includes__ = []
    __extends__ = None
    __rebase__ = None


Loosy coupled
-------------

Loosy coupled means you can inherit any class and change any external code dependency, without dealing with hardcoded cross-dependencies on classes, or functions.


Well tested
-----------

Nearly all code lines are covered by tests.

Features
========

As fast as the original
-----------------------
A different approach which delivers the same speed (a bit faster in some cases), but with a maintenable and extendible codebase.

Useful tracebacks
-----------------
TemplateRuntimeError prints a traceback pointing to original template code, and the exception object comes with userful debug info (line number and code for both python and original template code).

Bottle.py compatible
------------------------------------------
This project supports `bottle.py` 0.2 and 0.3 template syntax, and can be used as a drop-in replace.

.. _bottle.py: https://github.com/defnull/bottle

Template inheritance
--------------------

Stpl2 allows extends/block based template inheritance like other *bigger* template engines.

base.tpl

::

    % block my_block
    My base block content.
    % end

template.tpl

::

    % extends base
    % block my_block
    Base: {{ block.super }}
    My inherited block content.
    % end

output

::

    Base: My base block content.
    My inherited block content.

Template rebase
---------------

base.tpl

::

    My first line
    {{ base }}
    My third line

rebase.tpl

::

    % rebase base
    My second line

output

::

    My first line
    My second line
    My third line

Template include
----------------

include.tpl

::

    External line

template.tpl

::

    First line
    % include include
    Last line

output

::

    First line
    External line
    Last line

Stream by default
-----------------

Default template behavior is to stream templates using yielding without worrying about buffering. This approach have been choosen due most wsgi or proxy servers tends to buffer the responses themselves.

If buffering is a must for you, BufferingTemplate can be used, inheriting from TemplateManager class and overriding its template_class attribute.

BufferingTemplate can be customized in the same way in order to change the buffer size (the size of yielded chunks in bytes).

.. code-block:: python

    import stpl2

    class BufferingTemplate(stpl2.BufferingTemplate):
        buffersize = 3048 # buffering size in bytes

    class BufferingTemplateManager(stpl2.TemplateManager):
        template_class = Buffering_template


