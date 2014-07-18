#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
Stpl2
=====
Stpl 2 is a standalone reimplementation of bottle.py's SimpleTemplate Engine,
for better maintenability and performance, and with some extra features.

Features
~~~~~~~~
 * Templates are translated to generator functions (yield from is used if supported).
 * Readable and optimal python code generation.
 * Code block smart collapsing.
 * Supports include and rebase as in bottle.py's SimpleTemplate Engine.
 * Supports extends, block and block.super as in django templates.
 * Near-full tested.

Rules
~~~~~
 * Lines starting with '%' are translated to python code.
 * Lines starting with '% end' decrement indentation level.
 * Code blocks starts with '<%', and ends with '%>'.
 * Variable substitution starts with '{{', and ends with '}}'.

Usage
~~~~~

example.py

    #!/usr/bin/env python
    # -*- coding: UTF-8 -*-
    import stpl2
    manager = stpl2.TemplateManager("my/template/directory")
    manager.render("my_template", {"some":1,"vars":2})

my_template.tpl

    This is sort of template.
    With {{ some }} {{ vars }}.

'''

from .internal import (
    # Template
    BufferingTemplate, TemplateManager, Template,
    # Exceptions
    TemplateContextError, TemplateNotFoundError, TemplateRuntimeError,
    TemplateSyntaxError, TemplateValueError,
    # Public functions
    escape_html_safe,
    )

__app__ = 'stpl2'
__version__ = 0.3
__author__ = 'Felipe A. Hernandez <ergoithz@gmail.com>'
