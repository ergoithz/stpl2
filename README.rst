Stpl2
=====

.. image:: http://img.shields.io/travis/ergoithz/stpl2.svg?style=flat-square
  :target: https://travis-ci.org/ergoithz/stpl2
  :alt: Build status

.. image:: http://img.shields.io/coveralls/ergoithz/stpl2.svg?style=flat-square
  :target: https://coveralls.io/r/ergoithz/stpl2
  :alt: Test coverage

.. image:: http://img.shields.io/pypi/l/stpl2.svg?style=flat-square
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: License

.. image:: http://img.shields.io/pypi/v/stpl2.svg?style=flat-square
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: Latest Version

.. image:: http://img.shields.io/pypi/dm/stpl2.svg?style=flat-square
  :target: https://pypi.python.org/pypi/stpl2/
  :alt: Downloads

.. image:: https://img.shields.io/badge/python-2.6%2B%2C%203.3%2B-FFC100.svg?style=flat-square
  :alt: Python 2.6+, 3.3+

Stpl2 is a compatible reimplementation of `bottle.py's SimpleTemplate Engine`.

.. _bottle.py's SimpleTemplate Engine: http://bottlepy.org/docs/dev/stpl.html

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

Stpl2 is very simple, templates are parsed line by line, yielding readable high quality python code you can find on *Template.pycode* instance attribute, and then compiled, cached and wrapped on-demand into `TemplateContext` which cares about template inheritance, rebasing, updating variables and so on.


example.py

.. code-block:: python

    import stpl2

    manager = stpl2.TemplateManager('template_folder')
    template_iterator = manager.render('template', {'my_var': 'My variable'})
    template_string = ''.join(template_iterator)
    print(template_string)

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

Output

::

    Literal line
    My variable
    0
    1
    2
    3
    4


Loosy coupled
-------------

Loosy coupled means you can inherit any class and change any external code dependency, without dealing with hardcoded cross-dependencies on classes, or functions.


Well tested
-----------

Nearly all code lines are covered by tests.


Benchmarks
----------

This benchmarks' code are based on `Andriy Kornatskyy (akorn) benchmark suite`, adding bottle and stpl2 and removing mako, wheezy and tenjin (which seems to use some hacks which break other engines).

.. _Andriy Kornatskyy (akorn) benchmark suite: https://bitbucket.org/akorn/helloworld/

**cpython 3.4.1**

Note: bottle cannot run inheritance benchmarks due missing support.

.. image:: https://chart.googleapis.com/chart?chxt=x,y,y&chxl=0:|0k|5k|10k|15k|20k|25k|30k|35k|40k|45k|50k|55k|1:|tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle|2:||||and%20iterating%2010%20items|Inheritance%20and%20includes|||||and%20iterating%200%20items|Inheritance%20and%20includes|||||and%20iterating%2010%20items|Template%20with%204%20includes|||||and%20iterating%200%20items|Template%20with%204%20includes|||||and%20iterating%2010%20items|Basic%20template|||||and%20iterating%200%20items|Basic%20template&cht=bhs&chtt=renders%20per%20second&chd=t:56147,8976,32317,26589,40012,0,11865,916,9493,12319,9504,0,14717,4398,6950,6154,40710,0,7558,836,4394,4431,9527,0,0,2349,5715,3641,38440,0,0,696,3958,3118,9446&chds=0,60000&chbh=10,1,10&chs=500x446&chco=4BB7A4|92CC47|2F2F2F|969696|98CADE|4D8CBF
  :alt: Benchmark

**cpython 2.7.6**

.. image:: https://chart.googleapis.com/chart?chxt=x,y,y&chxl=0:|0k|5k|10k|15k|20k|25k|30k|35k|40k|45k|1:|tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle|2:||||and%20iterating%2010%20items|Inheritance%20and%20includes|||||and%20iterating%200%20items|Inheritance%20and%20includes|||||and%20iterating%2010%20items|Template%20with%204%20includes|||||and%20iterating%200%20items|Template%20with%204%20includes|||||and%20iterating%2010%20items|Basic%20template|||||and%20iterating%200%20items|Basic%20template&cht=bhs&chtt=renders%20per%20second&chd=t:43289,8810,37388,30984,48786,0,7161,887,10272,14316,12335,0,13280,4852,8374,7327,47265,0,5278,818,5181,5719,12503,0,0,2619,6838,4327,46425,0,0,724,4516,3611,12023&chds=0,50000&chbh=10,1,10&chs=500x446&chco=4BB7A4|92CC47|2F2F2F|969696|98CADE|4D8CBF

**pypy 2.3.1 (python 2.7.6)**

Note: tornado does not run on pypy.

.. image:: https://chart.googleapis.com/chart?chxt=x,y,y&chxl=0:|0k|10k|20k|30k|40k|50k|60k|70k|80k|90k|100k|110k|120k|130k|140k|150k|1:|tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle||tornado|stpl2|jinja2|django|bottle|2:||||and%20iterating%2010%20items|Inheritance%20and%20includes|||||and%20iterating%200%20items|Inheritance%20and%20includes|||||and%20iterating%2010%20items|Template%20with%204%20includes|||||and%20iterating%200%20items|Template%20with%204%20includes|||||and%20iterating%2010%20items|Basic%20template|||||and%20iterating%200%20items|Basic%20template&cht=bhs&chtt=renders%20per%20second&chd=t:107208,93845,151396,40454,0,0,36723,12672,33497,25747,0,0,27424,49707,5237,7573,0,0,17804,10516,4455,6692,0,0,0,21002,4372,4666,0,0,0,8565,3871,4306,0&chds=0,160000&chbh=10,1,10&chs=500x446&chco=4BB7A4|92CC47|2F2F2F|969696|98CADE|4D8CBF


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

Usage example
-------------

.. code-block:: python

    import stpl2

    manager = stpl2.TemplateManager(directories=['path/to/templates', 'more/templates'])

    # template lookup
    template = manager.get_template('template.tpl')

    # add template from string
    manager.templates['template2.tpl'] = stpl2.Template('Hello world, {{ name }}.', manager=manager)

    # rendering generator from manager
    template_generator = manager.render('template.tpl', {'foo': 'bar'})

    # rendering generator from template
    template_generator = template.render({'foo': 'bar'})

    # render and print template
    print(''.join(template_generator))

    # print template code and generated python code (useful for debugging)
    print(template.code)
    print(template.pycode)


Stream by default
-----------------

Default template behavior is to stream templates using yield without worrying about buffering. This approach have been choosen due most wsgi or proxy servers tends to buffer the responses themselves.

If buffering is a must for you, BufferingTemplate can be used, inheriting from TemplateManager class and overriding its template_class attribute.

BufferingTemplate can be customized in the same way in order to change the buffer size (the size of yielded chunks in bytes).

.. code-block:: python

    import stpl2

    class BufferingTemplate(stpl2.BufferingTemplate):
        buffersize = 3048 # buffering size in bytes

    class BufferingTemplateManager(stpl2.TemplateManager):
        template_class = BufferingTemplate


Using yield has a side effect, when you want a string you must join the generator object returned by render.

.. code-block:: python

    import stpl2

    manager = stpl2.TemplateManager('template_folder')
    template_generator = manager.render("my_template", {"template_variable":2})
    template_string = ''.join(template_iterator)
