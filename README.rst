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

This project aims full compatability with `bottle.py` `SimpleTemplate Engine` template syntax, and started as a replace for streaming templates using **yield**.  

.. _bottle.py: https://github.com/defnull/bottle
.. _SimpleTemplate Engine: http://bottlepy.org/docs/dev/stpl.html

Template inheritance
--------------------

In addition to **include** and **rebase** stuff, Stpl2 allows extends/block based template inheritance like other *bigger* template engines.

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

Stream by default
-----------------

Default template behavior is to stream templates using yielding without worrying about buffering.

In cases when buffering is a must BufferingTemplate can be used inheriting from TemplateManager class and overriding its template_class attribute.

  
