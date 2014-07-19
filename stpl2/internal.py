#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
Stpl2
=====
Please note only stuff exposed though __init__ module is considered public API

'''

import re
import sys
import zlib
import collections
import os
import os.path
import functools

# Py3k fixes
py3k = sys.version > '3'
if py3k:
    import builtins
    import html
    xrange = range
    iteritems = dict.items
    itervalues = dict.values
    unicode_prefix = ''
    base_notfounderror = FileNotFoundError
    yield_from_supported = sys.version_info.minor > 2
    maxint = sys.maxsize
    native_string_bases = (str,)
    tostr_safe = str

    def escape_html_safe(data):
        '''
        Parse given data to string and apply escape_html

        :param obj: any python object
        :return str: escaped html string
        '''
        return html.escape('%s' % data)
else:
    import __builtin__ as builtins
    import cgi
    iteritems = dict.iteritems
    itervalues = dict.itervalues
    unicode_prefix = 'u'
    base_notfounderror = IOError
    yield_from_supported = False
    maxint = sys.maxint
    native_string_bases = (basestring,)

    def tostr_safe(data):
        return '%s' % data

    def escape_html_safe(data):
        '''
        Parse given data to string and apply escape_html

        :param obj: any python object
        :return str: escaped html string
        '''
        return cgi.escape('%s' % data, quote=True).replace("'", "&apos;")


class TemplateSyntaxError(SyntaxError):
    pass


class TemplateContextError(ValueError):
    pass


class TemplateNotFoundError(base_notfounderror):
    pass


class TemplateValueError(ValueError):
    pass


class TemplateRuntimeError(RuntimeError):
    def __init__(self, error, code=None, lineno=None, pycode=None, pylineno=None):
        self.error = error
        self.code = code
        self.lineno = lineno
        self.pycode = pycode
        self.pylineno = pylineno

        context = []
        if code:
            cstart = max(lineno-5, 0)
            context.extend("    %s" % line for line in code[cstart:lineno-1])
            context.append(">>> %s" % code[lineno-1])
            context.extend("    %s" % line for line in code[lineno:lineno+3])
            message = "in line %d:" % lineno
        elif pycode:
            cstart = max(pylineno-4, 0)
            context.extend("    %s" % line for line in pycode[cstart:pylineno])
            context.append(">>> %s" % pycode[pylineno])
            context.extend("    %s" % line for line in pycode[pylineno+1:pylineno+4])
            message = "in unknown line. Generated code was:\n"
        else:
            message = "in unknown line"

        error_name = type(error).__name__
        error_message = str(error)

        # Error message unification
        if error_message.endswith("."):
            message = message.capitalize()
        elif error_message.strip()[-1].isalnum():
            message = ", %s" % message
        elif not error_message.endswith(" "):
            message = " %s" % message

        error = "%s: %s%s" % (error_name, error_message, message)
        if context:
            error = "%s\n%s" % (error, "\n".join(context))
        RuntimeError.__init__(self, error)


class CodeTranslator(object):
    '''
    Translate from SimpleTemplate Engine 2 syntax to Python code.
    '''
    syntax_error_class = TemplateSyntaxError
    value_error_class = TemplateValueError

    tab = "    "
    linesep = "\n"
    literal_open = "<%"
    literal_close = "%>"
    variable_open = "{{"
    variable_close = "}}"
    code_line_prefix = "%"

    indent_tokens = ("class", "def", "with", "if", "for", "while")
    redent_tokens = ("else", "elif", "except", "finally")
    custom_tokens = ("block", "block.super", "end", "extends", "include", "rebase", "base")

    def __init__(self):
        # compile regexps
        indent = r"((?P<indent>(%s))(?!\w))" % "|".join(re.escape(i) for i in self.indent_tokens)
        redent = r"((?P<redent>(%s))(?!\w))" % "|".join(re.escape(i) for i in self.redent_tokens)
        custom = r"((?P<custom>(%s))(?!\w)\s*(?P<params>((\s+.*)|(\(.*\)))\s*)?$)" % "|".join(re.escape(i) for i in self.custom_tokens)

        redict = {
            'string': r"(\'((\\.)|[^\'])*?\')|(\"((\\.)|[^\"])*?\")", # massive nongreedy string and escape sensitive dotall regexp
            'var_open': re.escape(self.variable_open),
            'var_close': re.escape(self.variable_close),
        }

        # regexp precompilation
        self.re_tokens = re.compile("^(%s)" % "|".join((indent, redent, custom)))
        self.re_var = re.compile("(%(var_open)s(?P<var>(%(string)s|.)*?)%(var_close)s)|(?P<escape>%%)" % redict)
        self.re_inline = re.compile("(\{(%(string)s)\}|(%(string)s)|.)*?:(?P<inline>.*)" % redict)

        self.code_line_prefix_length = len(self.code_line_prefix)

    @classmethod
    def param_split(cls, params, seps, valuesep, strip, quote='\'"',
                    must_quote=False, escape='\\', free_escape=False,
                    maxnum=maxint):
        '''
        Split a param string based on rules and return a  tuple with arguments,
        keyword arguments and unparsed data (see `maxnum` argument).

        :param string params: param string
        :param iterable seps: field separators
        :param iterable valuesep: key-value separator for keyword fields
        :param iterable strip: characters to strip outside quotes
        :param iterable quote: quote characters
        :param iterable escape: escape characters
        :param bool free_escape: wether allow escapes outside quoted values
        :param int maxnum: number of arguments will be parsed (default is all)
        :returns tuple: tuple with arguments list, keyword arguments dict and unparsed string.
        '''
        args = [[]]
        kwargs = {}
        quoted = None
        escaped = False
        key = None
        for p, char in enumerate(params):
            if escaped:
                escaped = False
                (kwargs[key] if key else args[-1]).append(char)
            elif char in escape and free_escape:
                escaped = True
            elif quoted:
                if char in escape:
                    escaped = True
                elif char == quoted:
                    quoted = None
                else:
                    (kwargs[key] if key else args[-1]).append(char)
            elif char in valuesep and not key:
                key = "".join(args.pop())
                kwargs[key] = []
            elif char in quote:
                quoted = char
            elif char in seps and (args[-1] or key):
                if len(args) + len(kwargs) < maxnum:
                    key = None
                    args.append([])
                else:
                    break
            elif not char in strip:
                (kwargs[key] if key else args[-1]).append(char)

        # strip
        extra = params[p+1:]
        for i in strip:
            extra = extra.strip(i)
        args = ["".join(i) for i in args]
        kwargs = dict((k, "".join(v)) for k, v in iteritems(kwargs))
        return args, kwargs, extra

    @classmethod
    def token_params(cls, params, maxnum=maxint):
        '''
        Parse custom token params detecting the correct parsing configuration
        for :py:method:param_split.

        :param string params: param string
        :param int maxnum: number of arguments will be parsed (default is all)
        :returns tuple: tuple with arguments list, keyword arguments dict and unparsed string.
        '''
        params = params.strip() if params else ""
        if params:
            if params.startswith("(") and params.endswith(")"):
                params = params[1:-1]
                valuesep = "="
                seps = ","
                free_escape = False
                must_quote = True
            else:
                valuesep = ""
                seps = ", "
                free_escape = True
                must_quote = False
            return cls.param_split(params, seps, valuesep, ", ",
                                   must_quote=must_quote,
                                   free_escape=free_escape, maxnum=maxnum)
        return (), {}, ""

    def check_indent(self, line):
        '''
        Get if current line should increment indent or not (if has inline code).
        :param string line: line of code with indent token
        :returns bool: True if line contains no inline code so must indent.
        '''
        match = self.re_inline.match(line)
        if match:
            stripped = match.groupdict().get("inline", "").strip()
            return not stripped or stripped.startswith("#")
        return True

    @property
    def indent(self):
        '''
        Get current indentation string, based in :py:cvar:tab and :py:var:level.

        :return string: current indent as string.
        '''
        return self.tab * self.level

    @property
    def dopass(self):
        if self.level == self.minlevel or self.block_stack and self.level == self.block_stack[-1][0]:
            return "%sif False: yield" % self.indent
        return "%spass" % self.indent


    def yield_string_start(self):
        '''
        :yield basestring: line with string start yield
        '''
        if self.first_string_line:
            self.level_touched = True
            self.first_string_line = False
            yield "%syield (" % self.indent
            self.level += 1

    def yield_string_finish(self):
        '''
        :yield basestring: line with string finish and substitution tuple
        '''
        if not self.first_string_line:
            self.level_touched = True
            self.first_string_line = True
            if self.string_vars:
                rtup = ", ".join(self.string_vars)
                suffix = "" if "," in rtup else ","
                yield "%s) %% (%s%s)" % (self.indent, rtup, suffix)
                del self.string_vars[:]
            else:
                yield "%s)" % self.indent
            self.level -= 1

    def yield_from_native(self, param):
        '''
        :yield basestring: line with yield from for supported python versions
        '''
        yield "%syield from %s" % (self.indent, param)

    def yield_from_legacy(self, param):
        '''
        :yield basestring: lines with for line in... yield line for legacy python versions
        '''
        yield "%sfor line in %s:" % (self.indent, param)
        self.level += 1
        yield "%syield line" % self.indent
        self.level -= 1

    yield_from = yield_from_native if yield_from_supported else yield_from_legacy

    def translate_var(self, match):
        '''
        Get variable string substitution (for re.sub) and store variable code.
        :return str: positional variable string substitution '%s'
        '''
        group = match.groupdict()
        if group.get('escape', None):
            return '%%'
        var = group.get('var', None)
        if var is None:
            return ''
        var = var.strip()
        # STPL awful bang ('!') modifier
        var = var[1:].lstrip() if var[0] == '!' else '_escape(%s)' % var
        self.string_vars.append(var)
        return "%s"

    def translate_token_end(self, params=None):
        '''
        Decrement current indentation level.
        :yield str: line pass if current block is empty
        '''
        if not self.level_touched:
            yield self.dopass
        self.level -= 1
        self.level_touched = True # level already touched by indent token
        if self.level < self.minlevel:
            if self.block_stack:
                # level below minimum cos we're ending current block
                self.level, name = self.block_stack.pop()
            else:
                # prevent writing lines at module level
                raise self.syntax_error_class("Unmatching 'end' token on line %d" % self.linenum)

    def translate_token_extends(self, params=None):
        '''
        Declare that current template is based on given one.
        '''
        # extends is managed by template context
        if self.level > self.minlevel or self.block_stack:
            raise self.syntax_error_class("Token 'extends' must be outside any block (line %d)." % self.linenum)
        elif not self.extends is None:
            raise self.syntax_error_class("Token 'extends' cannot be defined twice (line %d)." % self.linenum)
        args, kwargs, unparsed = self.token_params(params)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise self.value_error_class("Token 'extends' receives at least one argument: name (line %d)." % self.linenum)
        self.extends = name

    def translate_token_block(self, params=None):
        '''
        Generate lines for yielding block and starts block.
        :yield: lines for yielding from block
        '''
        # yield from block
        args, kwargs, unparsed = self.token_params(params, 1)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise self.value_error_class("Token 'block' receives at least one argument: name (line %d)." % self.linenum)
        params = ("%r, %s" % (name, unparsed)) if unparsed else repr(name)
        for line in self.yield_from("block(%s)" % params):
            yield line
        # start putting lines on new block
        self.block_stack.append((self.level, name))
        self.level = self.minlevel
        self.level_touched = False

    def translate_token_block_super(self, params=None):
        '''
        Generate lines for yielding for block with the same name on parent template.
        :yield: lines for yielding from parent block
        '''
        if not self.block_stack:
            raise self.syntax_error_class("Token 'block.super' outside any block (line %d)" % self.linenum)
        for line in self.yield_from("block.super"):
            yield line

    def translate_token_include(self, params=None):
        '''
        Generate lines for yielding for other template with given name.
        :yield: lines for yielding from external template.
        '''
        args, kwargs, unparsed = self.token_params(params, 1)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise self.value_error_class("Token 'include' receives at least one argument: name (line %d)." % self.linenum)
        params = ("%r, %s" % (name, unparsed)) if unparsed else repr(name)
        for line in self.yield_from("include(%s)" % params):
            yield line
        self.includes.append(name)

    def translate_token_rebase(self, params=None):
        '''
        Parses name from params and adds to :py:var:rebase which will be used
        later.
        '''
        args, kwargs, unparsed = self.token_params(params, 1)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise self.value_error_class("Token 'rebase' receives at least one argument: name (line %d)." % self.linenum)
        self.rebase = name

    def translate_token_base(self, params=None):
        '''
        :yield: lines for yielding base template
        '''
        for line in self.yield_from("base"):
            yield line

    def translate_code_line(self, data):
        '''
        Translate a template line with inline python code
        '''
        # Code line
        lstripped = data[self.code_line_prefix_length:].lstrip()
        try:
            group = self.re_tokens.match(lstripped).groupdict()
        except AttributeError:
            group = {'custom':None,'redent':None,'indent':None}
        if group['custom']:
            method = 'translate_token_%s' % group['custom'].replace('.', '_')
            for line in getattr(self, method)(group['params']) or ():
                yield line
        elif group['redent']:
            if not self.level_touched:
                yield self.dopass
            self.level -= 1
            yield self.indent + lstripped
            if self.check_indent(lstripped):
                self.level += 1
                self.level_touched = False
        else:
            if lstripped.strip():
                yield self.indent + lstripped
            if group['indent'] and self.check_indent(lstripped):
                self.level += 1
                self.level_touched = False

    def translate_string_line(self, data):
        '''
        Translate regular template line with or without variable substitutions.
        :yields: lines that's starts yielding string (if not already done) and string line.
        '''
        # String
        if data.strip():
            data = self.re_var.sub(self.translate_var, data)
            for i in self.yield_string_start():
                yield i
            yield '%s%r' % (self.indent, data)
        elif not self.inline:
            for i in self.yield_string_start():
                yield i
            yield '%s%r' % (self.indent, data)

    def translate_literal_line(self, data):
        '''
        Generator function for translating lines inside python code blocks.

        When a code block ending is reached, this function switches :py:var:translate_line
        to :py:method:translate_literal_line.
        '''
        template_data = None
        if self.literal_close in data:
            data, template_data = data.split(self.literal_close, 1)
        if self.base is None and data.strip():
            self.base = len(data) - len(data.lstrip())
        # Remove unnecessary 'pass' commands
        if not self.level_touched or data.strip() != "pass":
            for line in self.yield_string_finish():
                yield line
            yield self.indent + data[self.base:]
        if not template_data is None:
            # Reset
            self.base = None
            self.inline = False
            # Switch to template mode
            self.translate_line = self.translate_template_line
            if template_data.strip():
                for i in self.yield_string_start():
                    yield i
                if self.previous_indent:
                    yield "%s%r" % (self.indent, " " * self.previous_indent)
                for line in self.translate_line(template_data):
                    yield line
            elif self.previous_string:
                for i in self.yield_string_start():
                    yield i
                yield "%s%r" % (self.indent, self.linesep)

    def translate_template_line(self, data):
        '''
        Generator function for translating template lines.

        When a code block is reached, this function switches :py:var:translate_line
        to :py:method:translate_literal_line.
        '''
        literal_data = None
        if self.literal_open in data:
            data, literal_data = data.split(self.literal_open, 1)
            self.inline = True
        lstripped = data.lstrip()
        if lstripped.startswith(self.code_line_prefix):
            for line in self.yield_string_finish():
                yield line
            self.previous_string = False
            for line in self.translate_code_line(lstripped):
                yield line
        else:
            if self.inline:
                if data.strip():
                    self.previous_string = True
                    self.previous_indent = 0
                else:
                    self.previous_string = False
                    self.previous_indent = len(data) - len(lstripped)
            for line in self.translate_string_line(data):
                yield line
        if not literal_data is None:
            # Switch to literal mode
            self.translate_line = self.translate_literal_line
            for line in self.translate_line(literal_data):
                yield line

    def translate_code(self, data):
        '''
        Resets object state (see :py:method:reset) and generate python code
        that yields given data.

        :param str data: template string
        :yields str: generated lines of python code with endings
        '''
        self.reset()

        # Yield lines
        yield "# -*- coding: UTF-8 -*-%s" % self.linesep
        yield "def __template__():%s" % self.linesep
        oneline = False
        annotated = False
        for self.linenum, line in enumerate(data.splitlines(True), 1):
            annotated = False
            for part in self.translate_line(line):
                if part.endswith(self.linesep):
                    # needed for annotations, removes extra whitelines
                    part = part[:-1]
                if not annotated:
                    annotated = True
                    margin = 67 - len(part) - len("%d" % self.linenum)
                    part += ("#lineno:%d#" % self.linenum).rjust(margin)
                if self.block_stack:
                    block_line, block_name = self.block_stack[-1]
                    self.block_content[block_name].append(part)
                    continue
                oneline |= True
                yield part + self.linesep
        self.level = self.minlevel # Reset level
        if not oneline:
            # empty template, pass
            yield self.dopass + self.linesep
        else:
            for line in self.yield_string_finish():
                yield line + self.linesep
            del self.string_vars[:]
        # Yield blocks
        yield "__blocks__ = {}%s" % self.linesep
        for name, lines in iteritems(self.block_content):
            yield "def __block__(block):%s" % self.linesep
            oneline = False
            for linenum, line in enumerate(lines, 1):
                oneline |= True
                yield line + self.linesep
            if not oneline:
                yield self.dopass + self.linesep
            yield "__blocks__[%r] = __block__%s" % (name, self.linesep)

        # Yield metadata fields
        yield (
            "__includes__ = %r%s"
            "__extends__ = %r%s"
            "__rebase__ = %r%s"
            ) % (
            self.includes, self.linesep,
            self.extends, self.linesep,
            self.rebase, self.linesep,
            )

    def reset(self):
        '''
        Sets object to initial state
        '''
        self.inline = False # if True will skip linesep to string lines
        self.first_string_line = True
        self.unfinished_token = False
        self.base = None
        self.linenum = -1
        self.level = self.minlevel = 1
        self.translate_line = self.translate_template_line
        self.extends = None
        self.rebase = None
        self.includes = []
        self.string_vars = []
        self.block_stack = [] # list of block levels as (base, name)
        self.block_content = collections.defaultdict(list)
        self.level_touched = False


class StringGenerator(object):
    '''
    Generic generator wrapper which receives a generator factory function and
    arguments and allows iteration.
    '''
    __slots__ = ('_iterfunc', '_args', '_kwargs')

    def __init__(self, iterfunc=None, *args, **kwargs):
        self._iterfunc = iterfunc
        self._args = args
        self._kwargs = kwargs

    def __iter__(self):
        if self._iterfunc:
            return self._iterfunc(*self._args, **self._kwargs)
        return ()

    def __str__(self):
        return "".join(self)


class LocalBlockGenerator(StringGenerator):
    '''
    Block context variable inside blocks
    '''
    __slots__ = ('super',)

    def __init__(self, superfunc, *args, **kwargs):
        StringGenerator.__init__(self)
        self.super = StringGenerator(superfunc, *args, **kwargs)


class BlockGenerator(StringGenerator):
    '''
    Object retrieved by block function
    '''
    __slots__ = ('_name', '_superfunc')

    local_block_class = LocalBlockGenerator

    @property
    def super(self):
        return StringGenerator(self._superfunc, self.name)

    def __init__(self, iterfunc, superfunc, name):
        StringGenerator.__init__(self, iterfunc)
        self._name = name
        self._superfunc = superfunc

    def __iter__(self):
        local_block = self.local_block_class(self._superfunc, self._name, self.local_block_class)
        return self._iterfunc(local_block)


class TemplateContext(object):
    '''
    Template namespace boilerplate, interpret, manages context, inheritance and
    generator functions from given template code.

    Can be used as context manager.
    '''
    block_class = BlockGenerator
    base_class = StringGenerator
    include_class = StringGenerator
    context_error_class = TemplateContextError
    escape_html = staticmethod(escape_html_safe)
    tostr = staticmethod(tostr_safe)

    _context = None

    @property
    def template(self):
        '''
        Current template generator-function.
        '''
        if self.rebased:
            return self.rebased.template
        return self.base_template

    @property
    def base_template(self):
        '''
        Current non-rebased template generator-function
        '''
        if self.parent:
            return self.parent.template
        return self.owned_template

    @property
    def context(self):
        if self.rebased:
            return self.rebased.context
        return self.base_context

    @property
    def base_context(self):
        if self.parent:
            return self.parent.base_context
        return self.owned_context

    @property
    def namespace(self):
        if self.rebased:
            return self.rebased.namespace
        return self.base_namespace

    @property
    def base_namespace(self):
        if self.parent:
            return self.parent.base_namespace
        return self.owned_namespace

    @property
    def parentmost(self):
        if self.parent:
            return self.parent.parentmost or self.parent
        return None

    @property
    def childmost(self):
        if self.child:
            return self.child.childmost or self.child
        return None

    def iter_ancestors(self):
        '''
        Iterate over ancestors as in (self, parentmost].
        '''
        ancestor = self.parent
        while ancestor:
            yield ancestor
            ancestor = ancestor.parent

    def iter_descendants(self):
        '''
        Iterate over descendants as in (self, childmost].
        '''
        descendant = self.child
        while descendant:
            yield descendant
            descendant = descendant.child

    def __init__(self, code, manager=None):
        '''
        Create environment, evaluates given code object and set up context.
        '''
        self.manager = manager

        self.includes_cache = {}

        # Relations for rebase
        self.rebased = None
        self.base = ""

        # Relations for extends
        self.parent = None
        self.child = None

        # Inheritance contexts
        self.owned_context = {}
        self.owned_namespace = {}

        eval(code, self.owned_namespace)
        self.owned_template = self.owned_namespace["__template__"]

        self.blocks = self.owned_namespace["__blocks__"]
        self.includes = self.owned_namespace["__includes__"]

        self.extends = self.owned_namespace["__extends__"]
        self.rebase = self.owned_namespace["__rebase__"]

        if self.manager is None and (self.includes or self.extends or self.rebase):
            raise self.context_error_class("TemplateContext's extends, include and rebase require a template manager.")

        if self.includes:
            self.includes_cache.update(
                (name, self.manager.get_template(name).get_context())
                for name in self.includes
                )

        if self.extends:
            self.parent = self.manager.get_template(self.extends).get_context()
            self.parent.child = self

        if self.rebase:
            self.rebased = self.manager.get_template(self.rebase).get_context()
            self.rebased.builtins['base'] = self.base_class(self.iter_base)

        self.builtins = {}
        self.builtins.update(builtins.__dict__)
        self.builtins.update({
            # Ctx reference for debugging
            "__ctx__": self,
            # Backwards-compatible ugly vars
            "_stdout": None,
            "_printlist": None,
            "_rebase": None,
            "_str": self.tostr,
            "_escape": self.escape_html,
            # Global functions
            "include": self.get_include,
            "block": self.get_block,
            # Namespace methods
            "defined": self.owned_namespace.__contains__,
            "get": self.owned_namespace.get,
            "setdefault": self.owned_namespace.setdefault,
            # Updated by related TemplateContexts
            "base": None,
            })

        self.reset()

    def get_include(self, name, **environ):
        '''
        Get include iterable based on :py:cvar:include_class
        '''
        if not name in self.includes_cache:
            self.includes_cache[name] = self.manager.get_template(name).get_context()
        context = self.includes_cache[name]
        context.reset(False)
        context.update(self.context)
        context.owned_namespace.update(environ)
        return self.include_class(self.includes_cache[name].template)

    def get_block(self, name, **environ):
        '''
        Get block iterable based on :py:cvar:block_class
        '''
        child = self.childmost or self
        if name in child.blocks:
            context = child
        else:
            for child in child.iter_ancestors():
                if name in child.blocks:
                    context = child
                    break
        if context:
            context.reset(False)
            context.owned_namespace.update(self.context)
            context.owned_namespace.update(environ)
            return context.block_class(context.blocks[name], context.iter_super, name)

    def iter_base(self, **environ):
        '''
        Yield from rebased template
        '''
        context = self
        context.reset(False)
        context.base_context.update(self.context)
        context.base_namespace.update(self.context)
        context.base_namespace.update(environ)
        return self.base_template()

    def iter_super(self, name, local_block_class, **environ):
        '''
        Yield from parent block generator with given name
        '''
        context = None
        for parent in self.iter_ancestors():
            if name in parent.blocks:
                context = parent
                break
        if context:
            context.reset(False)
            context.owned_namespace.update(self.context)
            context.owned_namespace.update(environ)
            return context.blocks[name](local_block_class(context.iter_super, name, local_block_class))
        return ()

    def reset(self, full_reset=True):
        '''
        Clears and repopulate template namespace

        :param bool reset_context: Whether (defaults to True) clean user-defined context vars

        '''
        if full_reset:
            if self.rebased:
                self.rebased.reset()
            self.base_context.clear()
        self.owned_namespace.clear()
        self.owned_namespace.update(self.builtins)

    def update(self, v):
        '''
        Add given iterable to namespace.
        '''
        self.context.update(v)
        self.namespace.update(v)


class Template(object):
    '''
    Template class using a template context-function pool for thread-safety.
    '''

    translate_class = CodeTranslator
    template_context_class = TemplateContext
    runtime_error_class = TemplateRuntimeError
    lineno_annotation_re = re.compile("^.*#lineno:(?P<lineno>\d+)#$")

    @property
    def pycode(self):
        return zlib.decompress(self._pycode).decode("utf-8")

    def __init__(self, code, filename=None, manager=None):
        self.filename = filename
        self.manager = manager
        self.code = code

        pycode = "".join(self.translate_class().translate_code(code))

        self._pycode = zlib.compress(pycode.encode("utf-8"))
        self._pycompiled = compile(pycode, filename or "<template>", "exec")
        self._pool = []

    def get_context(self, env=None):
        '''
        Generate or retrieve from pool a template context object for
        thread-safety usage.

        :param dict env: environment dictionary
        :returns TemplateContext: template context object
        '''
        if self._pool:
            context = self._pool.pop()
        else:
            context = self.template_context_class(self._pycompiled, self.manager)
        if env:
            context.update(env)
        return context

    def render(self, env=None):
        '''
        Renders template updating global namespace with env dict-like object.

        :param dict env: environment dictionary
        :yields str: template lines as string
        :raise TemplateRuntimeError: on any template exception.
        '''
        context = self.get_context(env)
        try:
            # Yielding here for proper error handling
            for line in context.template():
                yield line
        except BaseException as e:
            type, value, traceback = sys.exc_info()

            # Get exception template context
            tb_next = traceback
            while tb_next.tb_next:
                tb_next = tb_next.tb_next
            tb_ctx = tb_next.tb_frame.f_globals.get('__ctx__')
            if tb_ctx is None:
                raise

            # Get related template object
            template = None
            if tb_ctx is context:
                template = self
            elif self.manager:
                # Search for reference recursively
                queue = [context]
                candidates = {}
                while queue:
                    # Inspect reachable contexts
                    ctx = queue.pop()
                    candidates.clear()
                    if ctx.rebase:
                        candidates[ctx.rebase] = ctx.rebased
                    if ctx.extends:
                        candidates[ctx.extends] = ctx.parent
                    candidates.update(ctx.includes_cache)
                    # Check if one of candidates is reference
                    for name, cctx in iteritems(candidates):
                        if cctx is tb_ctx:
                            template = self.manager.get_template(name)
                            break
                        queue.append(cctx)
                    else:
                        continue
                    break

            # Generate exception
            if template:
                pycode = template.pycode.splitlines()
                pycode_lineno = tb_next.tb_lineno-1
                code_lineno = None

                # Search template line looking at annotations
                for lineno in xrange(pycode_lineno, -1, -1):
                    match = self.lineno_annotation_re.match(pycode[lineno])
                    if match:
                        code_lineno = int(match.groupdict()['lineno'], 10)
                        break
                else:
                    # should not happen
                    raise self.runtime_error_class(value,
                        pycode=pycode, pylineno=pycode_lineno
                        )
                raise self.runtime_error_class(value,
                    code=template.code.splitlines(), lineno=code_lineno,
                    pycode=pycode, pylineno=pycode_lineno
                    )
            raise self.runtime_error_class(value)
        finally:
            context.reset()
            self._pool.append(context)


class BufferingTemplate(Template):
    '''
    Template which yields buffered chunks of :py:cvar:buffersize size.

    You may want to inherit from this class in order to define a different
    value or, alternatively, change it once object is initialized.
    '''
    buffersize = 4096

    def render(self, env=None):
        '''
        Renders template updating global namespace with env dict-like object.
        Additionaly, this function ensures all-but-last yielded strings have
        the same length defined in :py:cvar:buffersize.

        :param dict env: environment dictionary
        :yields str: template lines as string
        '''
        buffsize = 0
        cache = []
        for line in Template.render(self, env):
            cache.append(line)
            buffsize += len(line)
            # Buffering
            while buffsize > self.buffersize:
                data = "".join(cache)
                yield data[:self.buffersize]
                data = data[self.buffersize:]
                cache[:] = (data,) if data else ()
                buffsize = len(data)
        if cache:
            yield "".join(cache)


class TemplateManager(object):
    '''
    Template manager is responsible of Template loading and caching, and should
    be instanced once for your application.

    Please consider that template parsing, compiling and running is much slower
    than taken a precompiled template from cache, so using this class is
    absolutely recommended.
    '''
    template_class = Template
    notfound_error_class = TemplateNotFoundError
    template_extensions = (".tpl", ".stpl")

    @staticmethod
    def _ensure_set(obj):
        '''
        Ensure given object is correctly converted to a set.

        :param obj: any python object
        :return set: set containing obj or elements from obj if non-string iterable.
        '''
        if obj is None:
            return set()
        elif isinstance(obj, native_string_bases):
            return set((obj,))
        elif not isinstance(obj, set):
            return set(obj)
        return obj

    def __init__(self, directories=None):
        self.directories = self._ensure_set(directories)
        self.templates = {}

    def get_template(self, name):
        '''
        Get template object from given name from cache, template directories, or path.

        Note that template is cached based on given name, so if you pass to this method an absolute path, it will be the key from cache.

        :param str name: name of template (path or name if extension is in :py:cvar:template_extensions)
        :return Template: template object
        '''
        if not name in self.templates:
            template_path = None
            if not os.path.isabs(name):
                for directory in self.directories:
                    path = os.path.join(directory, name)
                    if os.path.isfile(path):
                        template_path = path
                        break
                    for ext in self.template_extensions:
                        extpath = path + ext
                        if os.path.isfile(extpath):
                            template_path = extpath
                            break
                    else:
                        continue
                    break
            elif os.path.exists(name):
                template_path = name
            if template_path is None:
                raise self.notfound_error_class("Template %r not found" % name)
            with open(template_path) as f:
                self.templates[name] = Template(f.read(), template_path, self)
        return self.templates[name]

    def render(self, name, env=None):
        '''
        Render template corresponding to given name or path.

        :param str name: name or path for template
        :param dict env: optional variable dictionary
        :yield str: string with lines from rendered template
        '''
        return self.get_template(name).render(env)

    def reset(self):
        '''
        Clear template cache.
        '''
        self.templates.clear()
