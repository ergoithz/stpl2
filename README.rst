Stpl2
=====

.. image:: https://travis-ci.org/ergoithz/stpl2.png?branch=master
  :target: https://travis-ci.org/ergoithz/stpl2

.. image:: https://coveralls.io/repos/ergoithz/stpl2/badge.png
  :target: https://coveralls.io/r/ergoithz/stpl2

Stpl2 (formerly SimpleTemplate Engine 2) is a compatible reimplementation of bottle-py's SimpleTemplate Engine.

Install
=======

Stpl2 is under active development and cannot be considered production-ready, said this, if you're brave enough, you can install using pip from this repo.

.. code-block:: bash

    pip install https://github.com/ergoithz/stpl2.git

Overview
========

This project aims full compatibility with `bottle.py` `SimpleTemplate Engine` template syntax, and started as a replace for streaming templates using **yield**.

.. _bottle.py: https://github.com/defnull/bottle
.. _SimpleTemplate Engine: http://bottlepy.org/docs/dev/stpl.html

Simple, loosy coupled and well tested
-------------------------------------
Stpl2 is very simple, templates are parsed by lines, yielding python code stored `Template`.`pycode` instance attribute, and then is compiled and wrapped using the TemplateContext which cares about template inheritance, rebasing, updating globals with context and so on.

Loosy coupled means you can inherit any class and change any external code dependency, without dealing with hardcoded cross-dependencies on classes, or functions.

Nearly all code lines are covered by tests.

Features
========

As fast as the original
-----------------------
A different approach which delivers the same speed (a bit faster in some cases), but with a maintenable and extendible code base.

Useful tracebacks
-----------------
TemplateRuntimeError prints a useful traceback and comes with a original and generated code, offending lines in original template and generated python code.

Bottle.py SimpleTemplate Engine compatible
------------------------------------------
This project supports `bottle.py` 0.2 and 0.3-dev template code, and can be used as a drop-in replace.

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


Stream by default
-----------------

Default template behavior is to stream templates using yielding without worrying about buffering. This approach have been choosen due most wsgi or proxy servers tends to buffer the responses themselves.

But, if buffering is a must for you, BufferingTemplate can be used, inheriting from TemplateManager class and overriding its template_class attribute.

::

    import stpl2

    class BufferingTemplateManager(stpl2.TemplateManager):
        template_class = stpl2.Buffering_template


