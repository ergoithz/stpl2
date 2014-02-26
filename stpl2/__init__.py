#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import re
import sys
import zlib
import argparse
import collections
import os
import os.path

# Py3k fixes
py3k = sys.version_info.major > 2
if py3k:
    import builtins
    iteritems = dict.items
    unicode_prefix = ''
    base_notfounderror = FileNotFoundError
    yield_from_supported = sys.version_info.minor > 2

    def escape_string(data):
        return data.encode('unicode_escape').decode('ascii')
else:
    import __builtin__ as builtins
    iteritems = dict.iteritems
    unicode_prefix = 'u'
    base_notfounderror = IOError
    yield_from_supported = False

    def escape_string(data):
        return data.encode("unicode_escape")


class TemplateSyntaxError(SyntaxError):
    pass


class TemplateContextError(ValueError):
    pass


class TemplateNotFoundError(base_notfounderror):
    pass


class TemplateValueError(ValueError):
    pass


class CodeTranslator(object):
    '''
    Translate from SimpleTemplate Engine 2 syntax to Python code.

    Rules
    ~~~~~
     * Lines starting with '%' are translated to python code.
     * Lines starting with '% end' decrement indentation level.
     * Code blocks starts with '<%', and ends with '%>'.
     * Variable substitution starts with '{{', and ends with '}}'.

    Features
    ~~~~~~~~
     * Generator-function based templates.
     * Yield from is used if supported by current python version.
     * Readable and optimal code output.
     * Code block start and/or ending lines are collapsed if empty.
     * Keyword 'pass' is omitted when unnecessary and automaticaly predicted for inline code.
     * Multiple lines are collapsed into a single yield.
     * Extends/block functionality.
     * Includes also supported.

    '''
    tab = "    "
    linesep = "\n"
    literal_open = "<%"
    literal_close = "%>"
    variable_open = "{{"
    variable_close = "}}"
    code_line_prefix = "%"

    indent_tokens = {"class", "def", "with", "if", "for", "while"}
    redent_tokens = {"else", "elif", "except", "finally"}
    custom_tokens = {"block", "block.super", "end", "extends", "include"}

    def __init__(self):
        '''
        '''
        # Compile regexps
        indent = "((?P<indent>(%s))(?!\w))" % "|".join(re.escape(i) for i in self.indent_tokens)
        redent = "((?P<redent>(%s))(?!\w))" % "|".join(re.escape(i) for i in self.redent_tokens)
        custom = "((?P<custom>(%s))(?!\w)\s*(?P<params>((\s+.*)|(\(.*\)))\s*)?$)" % "|".join(re.escape(i) for i in self.custom_tokens)
        self.re_tokens = re.compile("^(%s)" % "|".join((indent, redent, custom)))
        self.re_var = re.compile("%s(.*)%s" % (
            re.escape(self.variable_open),
            re.escape(self.variable_close)
            ))
        self.code_line_prefix_length = len(self.code_line_prefix)
        self.linesep_escaped = escape_string(self.linesep)

    @classmethod
    def param_split(cls, params, seps, valuesep, strip, quote='\'"',
                    must_quote=False, escape='\\', free_escape=False,
                    maxnum=sys.maxint):
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
        return map("".join, args), dict((k, "".join(v)) for k, v in iteritems(kwargs)), extra

    @classmethod
    def token_params(cls, params, maxnum=sys.maxint):
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

    @property
    def indent(self):
        '''
        Get current indentation string, based in :py:cvar:tab and :py:var:level.

        :return string: current indent as string.
        '''
        return self.tab * self.level

    def yield_string_start(self):
        '''
        :yield basestring: line with string start yield
        '''
        if self.first_string_line:
            self.level_touched = True
            self.first_string_line = False
            yield self.indent + "yield ("
            self.level += 1

    def yield_string_finish(self):
        '''
        :yield basestring: line with string finish and substitution tuple
        '''
        if not self.first_string_line:
            self.level_touched = True
            self.first_string_line = True
            if self.string_vars:
                yield "%s) %% (%s)" % (self.indent, ",".join(self.string_vars))
                del self.string_vars[:]
            else:
                yield "%s)" % self.indent
            self.level -= 1

    def yield_from_native(self, param):
        '''
        :yield basestring: line with yield from for supported python versions
        '''
        yield self.indent + "yield from %s" % param

    def yield_from_legacy(self, param):
        '''
        :yield basestring: lines with for line in... yield line for legacy python versions
        '''
        yield self.indent + "for line in %s:" % param
        self.level += 1
        yield self.indent + "yield line"
        self.level -= 1

    yield_from = yield_from_native if yield_from_supported else yield_from_legacy

    def translate_var(self, match):
        '''
        Get variable string substitution (for re.sub) and store variable code.
        :return str: positional variable string substitution '%s'
        '''
        self.string_vars.append(match.groups()[0])
        return "%s"

    def translate_token_end(self, params=None):
        '''
        Decrement current indentation level.
        :yield str: line pass if current block is empty
        '''
        if not self.level_touched:
            yield self.indent + "pass"
        self.level -= 1
        self.level_touched = True # level already touched by indent token
        if self.level < self.minlevel:
            if self.block_stack:
                # level below minimum cos we're ending current block
                self.level, name = self.block_stack.pop()
            else:
                # prevent writing lines at module level
                raise TemplateSyntaxError("Unmatching 'end' token on line %d" % self.linenum)

    def translate_token_extends(self, params=None):
        '''
        Declare that current template is based on given one.
        '''
        # extends is managed by template context
        if self.level > self.minlevel or self.block_stack:
            raise TemplateSyntaxError("Token 'extends' must be outside any block (line %d)." % self.linenum)
        elif not self.extends is None:
            raise TemplateSyntaxError("Token 'extends' cannot be defined twice (line %d)." % self.linenum)
        args, kwargs, unparsed = self.token_params(params)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise TemplateValueError("Token 'extends' receives at least one parameter: name (line %d)." % self.linenum)
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
            raise TemplateValueError("Token 'block' receives at least one parameter: name (line %d)." % self.linenum)
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
            raise TemplateSyntaxError("Token 'block.super' outside any block (line %d)" % self.linenum)
        for line in self.yield_from("block.super()"):
            yield line

    def translate_token_include(self, params=None):
        '''
        Generate lines for yielding for other template with given name.
        :yield: lines for yielding from external template.
        '''
        args, kwargs, unparsed = self.token_params(params, 1)
        name = kwargs.get("name", args[0] if args else None)
        if name is None:
            raise TemplateValueError("Token 'include' receives at least one parameter: name (line %d)." % self.linenum)
        params = ("%r, %s" % (name, unparsed)) if unparsed else repr(name)
        for line in self.yield_from("include(%s)" % params):
            yield line
        self.includes.append(name)

    def translate_code_line(self, data):
        '''
        Translate a template line with inline python code
        '''
        # Code line
        lstripped = data[self.code_line_prefix_length:].lstrip()
        group = self.re_tokens.match(lstripped).groupdict()
        if group['custom']:
            method = 'translate_token_%s' % group['custom'].replace('.', '_')
            for line in getattr(self, method)(group['params']) or ():
                yield line
        elif group['redent']:
            if not self.level_touched:
                yield self.indent + 'pass'
            self.level -= 1
            yield self.indent + lstripped
            self.level += 1
            self.level_touched = False
        else:
            if lstripped.strip():
                yield self.indent + lstripped
            if group['indent']:
                self.level += 1
                self.level_touched = False

    def translate_string_line(self, data):
        '''
        Translate regular template line with or without variable substitutions.

        '''
        # String
        if data.strip():
            data = self.re_var.sub(self.translate_var, data.replace("%", "%%"))
            data = escape_string(data)
            trail = "" if self.inline else self.linesep_escaped
            for i in self.yield_string_start():
                yield i
            yield "%s%s\"%s%s\"" % (self.indent, unicode_prefix, data, trail)
        elif not self.inline:
            for i in self.yield_string_start():
                yield i
            yield "%s%s\"%s%s\"" % (self.indent, unicode_prefix, data, self.linesep_escaped)

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
                    yield "%s%s\"%s\"" % (self.indent, unicode_prefix, " " * self.previous_indent)
                for line in self.translate_line(template_data):
                    yield line
            elif self.previous_string:
                for i in self.yield_string_start():
                    yield i
                yield "%s%s\"%s\"" % (self.indent, unicode_prefix, self.linesep_escaped)

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
        for self.linenum, line in enumerate(data.splitlines()):
            for part in self.translate_line(line):
                if self.block_stack:
                    block_line, block_name = self.block_stack[-1]
                    self.block_content[block_name].append(part)
                    continue
                yield part + self.linesep
        for line in self.yield_string_finish():
            yield line + self.linesep
        del self.string_vars[:]

        # Yield blocks
        yield "__blocks__ = {}%s" % self.linesep
        for name, lines in iteritems(self.block_content):
            yield "def __block__(block):%s" % self.linesep
            for line in lines:
                yield line + self.linesep
            yield "__blocks__[%r] = __block__%s" % (name, self.linesep)

        # Yield metadata fields
        yield "__includes__ = %r%s" % (self.includes, self.linesep)
        yield "__extends__ = %r%s" % (self.extends, self.linesep)

    def reset(self):
        '''
        Sets object to initial state
        '''
        self.inline = False # if True will skip linesep to string lines
        self.first_string_line = True
        self.unfinished_token = False
        self.base = None
        self.level = self.minlevel = 1
        self.translate_line = self.translate_template_line
        self.extends = None
        self.includes = []
        self.string_vars = []
        self.block_stack = [] # list of block levels as (base, name)
        self.block_content = collections.defaultdict(list)
        self.level_touched = False


class LocalBlock(object):
    '''
    Object will be passed to block as local 'block' variable.
    '''
    def __init__(self, template_context, name):
        self.template_context = template_context
        self.name = name

    def __call__(self, name, **environ):
        for line in self.template_context.block(name, **environ):
            yield line

    def super(self, **environ):
        for line in self.template_context.block_super(self.name, **environ):
            yield line


class TemplateContext(object):
    '''
    Manage context, env and evaluated generators from given template code.
    '''
    local_block_class = LocalBlock

    @property
    def template(self):
        '''
        Current template generator-function.
        '''
        if self.parent:
            return self.parent.template
        return self.owned_template

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

    def __init__(self, code, pool, manager=None):
        '''
        Create environment, evaluates given code object and set up context.
        '''
        self.pool = pool
        self.manager = manager
        self.namespace = {}
        self.includes = {}
        self.parent = None
        self.child = None

        eval(code, self.namespace)
        self.owned_template = self.namespace["__template__"]
        self.owned_includes = self.namespace["__includes__"]

        self.blocks = self.namespace["__blocks__"]
        self.extends = self.namespace["__extends__"]

        if self.extends:
            if self.manager is None:
                raise TemplateContextError("TemplateContext's extends requires manager to be passed.")
            self.parent = self.manager.get_template_context(self.extends)
            self.parent.child = self

        self.reset() # clean namespace

    def __enter__(self):
        return self.template

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.reset()
        self.pool.append(self)

    def include(self, name, **environ):
        # TODO: optimize
        context = self.manager.get_template_context(name)
        context.reset()
        context.update(environ)
        with context as render_func:
            for line in render_func():
                yield line

    def get_local_block(self, name):
        return self.local_block_class(self, name)

    def block(self, name, **environ):
        child = self.childmost or self
        if name in child.blocks:
            context = child
        else:
            for child in child.iter_ancestors():
                if name in child.blocks:
                    context = child
                    break
        if context:
            context.reset()
            context.update(environ)
            for line in context.blocks[name](context.get_local_block(name)):
                yield line

    def block_super(self, name, **environ):
        context = None
        for parent in self.iter_ancestors():
            if name in parent.blocks:
                context = parent
                break
        if context:
            context.reset()
            context.update(environ)
            for line in context.blocks[name](context.get_local_block(name)):
                yield line

    def reset(self):
        '''
        Clears and repopulate template namespace
        '''
        self.namespace.clear()
        self.namespace.update(builtins.__dict__)
        self.namespace.update({
            # Inheritance vars
            "include": self.include,
            "block": self.block,
            # Global functions
            "defined": self.namespace.__contains__,
            "get": self.namespace.get,
            "setdefault": self.namespace.setdefault,
            })

    def update(self, v):
        '''
        Add given iterable to namespace.
        '''
        self.namespace.update(v)


class Template(object):
    '''
    Template class using a template context-function pool for thread-safety.
    '''
    translate_class = CodeTranslator
    template_context_class = TemplateContext

    @property
    def code(self):
        return self._code

    @code.setter
    def code(self, v):
        pycode = "".join(self.translate_class().translate_code(v))
        self._code = v
        self._pycode = zlib.compress(pycode.encode("utf-8"))
        self._pycompiled = compile(pycode, self.filename or "<template>", "exec")

    @property
    def pycode(self):
        return zlib.decompress(self._pycode).decode("utf-8")

    @property
    def pycompiled(self):
        return self._pycompiled

    def __init__(self, code, filename=None, manager=None):
        self.filename = filename
        self.manager = manager
        self.code = code
        self.pool = []

    def template_context(self, env=None):
        '''
        Generate the new template generator function
        '''
        if self.pool:
            context = self.pool.pop()
        else:
            context = self.template_context_class(self._pycompiled, self.pool, self.manager)
        if env:
            context.update(env)
        return context

    def render(self, env=None):
        with self.template_context(env) as render_func:
            for line in render_func():
                yield line


class BufferingTemplate(Template):
    buffersize = 4096

    def render(self, env=None):
        with self.template_context(env) as render_func:
            buffsize = 0
            cache = []
            for line in render_func():
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
    template_class = Template
    template_extensions = (".tpl", ".stpl")

    def __init__(self, directories=None):
        self.directories = [] if directories is None else directories
        self.templates = {}

    def get_template(self, name):
        '''
        Get template object from given name.
        '''
        if not name in self.templates:
            template_path = None
            for directory in self.directories:
                path = os.path.join(directory, name)
                if os.path.isfile(path):
                    template_path = path
                    break
                for ext in self.template_extensions:
                    path += ext
                    if os.path.isfile(path):
                        template_path = path
                        break
                else:
                    continue
                break
            else:
                raise TemplateNotFoundError("Template %r not found" % name)
            with open(template_path) as f:
                self.templates[name] = Template(f.read(), template_path, self)
        return self.templates[name]

    def get_template_context(self, name):
        '''
        Get template context corresponding to template with given name.
        '''
        return self.get_template(name).template_context()

    def render_template(self, name, env=None):
        '''
        Render template corresponding
        '''
        template = self.get_template(name)
        for line in template.render(env):
            yield line

    def reset(self):
        '''
        Clear template cache.
        '''
        self.templates.clear()
