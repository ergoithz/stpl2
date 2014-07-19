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
 * Literal block smart collapsing.
 * Supports include and rebase as in bottle.py's SimpleTemplate Engine.
 * Supports extends, block and block.super as in django templates.
 * Near-full tested.

Rules
~~~~~
 * Lines starting with '%' are translated to python code.
 * Lines with '% end' decrement indentation level.
 * Code blocks starts with '<%', and ends with '%>'.
 * Variable substitution starts with '{{', and ends with '}}'.
 * Variables are escaped unless starting with '!' like '{{ ! safe_var }}'.

Usage
~~~~~

example.py

    #!/usr/bin/env python
    # -*- coding: UTF-8 -*-
    import stpl2
    manager = stpl2.TemplateManager("my/template/directory")
    output = manager.render("my_template", {"number":2, "things": "variables"})
    print(output)

my_template.tpl

    This my template.
    With {{ number }} {{ things }}.

output

    This is my template.
    With 2 variables.

'''

from .internal import (
    # Template
    BufferingTemplate, TemplateManager, Template,
    # Exceptions
    TemplateContextError, TemplateNotFoundError, TemplateRuntimeError,
    TemplateSyntaxError, TemplateValueError,
    # Public functions
    escape_html_safe, tostr_safe,
    )

__version__ = '0.2.2'
__license__ = 'MIT'
__author__ = 'Felipe A. Hernandez <ergoithz@gmail.com>'

