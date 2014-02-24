#!/usr/bin/env python
# -*- coding: UTF-8 -*-


import re
import sys
import zlib
import collections

# Py3k fixes
try:
    import __builtin__ as builtins
except ImportError:
    import builtins

try:
    iteritems = dict.iteritems
except AttributeError:
    iteritems = dict.items


class TemplateSyntaxError(SyntaxError):
    pass


class TemplateContextError(ValueError):
    pass


class CodeTranslator(object):
    '''
    Translate from SimpleTemplateLanguage to Python code.

    Rules:
        Lines starting with '%' are translated to python code.
        Lines starting with '% end' decrement indentation level.
        Code blocks starts with '<%', and ends with '%>'.
        Substitution variables starts with '{{', and ends with '}}'.

    Features:
        Readable and well indented code output.
        Lines containing only a code block start and/or ending are collapsed.
        Keyword 'pass' is omitted when unnecessary.
        Keyword 'pass' is automaticaly predicted for non-block code.
        Multiple lines are collapsed into a single yield.

    '''
    tab = "    "
    linesep = "\n"
    literal_open = "<%"
    literal_close = "%>"
    variable_open = "{{"
    variable_close = "}}"
    code_line_prefix = "%"

    indent_tokens = {"class", "def", "with", "if", "for", "while", "block"}
    redent_tokens = {"else", "elif", "except", "finally"}
    custom_tokens = {"block", "block.super", "end", "extends", "include"}

    def __init__(self):
        # Compile regexps
        indent = "((?P<indent>(%s)).*)" % "|".join(self.indent_tokens)
        redent = "((?P<redent>(%s)).*)" % "|".join(self.redent_tokens)
        custom = "((?P<custom>(%s))\s*(\((?P<func_params>.+)\))?\s*)" % "|".join(self.custom_tokens)
        self.re_tokens = re.compile("^(%s)$" % "|".join((indent, redent, custom)))
        self.re_var = re.compile("%s(.*)%s" % (self.variable_open, self.variable_close))

    def re_var_sub(self, match):
        self.string_vars.append(match.groups()[0])
        return "%s"

    def parse_token_params(self, params):
        if params and params.startswith("(") and params.endswith(")"):
            return eval("(lambda *args, **kwargs: args, kwargs)%s" % params)
        return (), {}

    @property
    def indent(self):
        return self.tab * self.level

    def escape_string_py3(self, data):
        return repr(data)[2 if isinstance(data, bytes) else 1:-1]

    def escape_string_py2(self, data):
        return data.encode("unicode-escaped")

    escape_string = escape_string_py2 if sys.version_info.major == 2 else escape_string_py3
    unicode_prefix = "u" if sys.version_info.major == 2 else ""

    def translate_token_end(self, params=None):
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
        # extends is managed by template context
        if self.level > self.minlevel:
            raise TemplateSyntaxError("Token 'extends' must be outside any block (line %d)." % self.linenum)
        elif not self.extends is None:
            raise TemplateSyntaxError("Token 'extends' cannot be defined twice (line %d)." % self.linenum)
        name = lstripped.split(" ", 1)[1].strip()
        self.extends = self.strip_str(name)

    def translate_token_block(self, params=None):
        # yield from block
        name = lstripped.split(" ", 1)[1].strip()
        yield self.indent + "for line in __blocks__[%r]():" % name
        self.level += 1
        yield self.indent + "yield line"
        # start putting lines on new block
        self.block_stack.append((self.level, name))
        self.level = self.minlevel
        self.level_touched = False

    def translate_token_block_super(self, params=None):
        if not self.block_stack:
            raise TemplateSyntaxError("Token 'block.super' outside any block (line %d)" % self.linenum)
        name = self.block_stack[-1][1]
        yield self.indent + "for line in __parent_blocks__[%r]():" % name
        self.level += 1
        yield self.indent + "yield line"
        self.level -= 1

    def translate_token_include(self, params=None):
        args, kwargs = self.parse_token_params(params)

    def translate_code_line(self, data):
        # Code line
        lstripped = data[self.code_line_prefix_length:].lstrip()
        group = self.re_tokens.match(lstripped).groupdict()
        if group['custom']:
            method = 'translate_token_%s' % group['custom'].replace('.', '_')
            for line in getattr(self, method)(group['func_params']):
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
        # String
        if data.strip():
            data = self.re_var.sub(self.re_var_sub, data.replace("%", "%%"))
            data = self.escape_string(data)
            trail = "" if self.inline else self.linesep_escaped
            for i in self.string_start():
                yield i
            yield "%s%s\"%s%s\"" % (self.indent, self.unicode_prefix, data, trail)
        elif not self.inline:
            for i in self.string_start():
                yield i
            yield "%s%s\"%s%s\"" % (self.indent, self.unicode_prefix, data, self.linesep_escaped)

    def translate_literal_line(self, data):
        template_data = None
        if self.literal_close in data:
            data, template_data = data.split(self.literal_close, 1)
        if self.base is None and data.strip():
            self.base = len(data) - len(data.lstrip())
        # Remove unnecessary 'pass' commands
        if not self.level_touched or data.strip() != "pass":
            for line in self.string_finish():
                yield line
            yield self.indent + data[self.base:]
        if not template_data is None:
            # Reset
            self.base = None
            self.inline = False
            # Switch to template mode
            self.translate_line = self.translate_template_line
            if template_data.strip():
                for i in self.string_start():
                    yield i
                if self.previous_indent:
                    yield "%su\"%s\"" % (self.indent, " " * self.previous_indent)
                for line in self.translate_line(template_data):
                    yield line
            elif self.previous_string:
                for i in self.string_start():
                    yield i
                yield "%su\"%s\"" % (self.indent, self.linesep_escaped)

    def string_start(self):
        if self.first_string_line:
            self.level_touched = True
            self.first_string_line = False
            yield self.indent + "yield ("
            self.level += 1

    def string_finish(self):
        if not self.first_string_line:
            self.level_touched = True
            self.first_string_line = True
            if self.string_vars:
                yield "%s) %% (%s)" % (self.indent, ",".join(self.string_vars))
                del self.string_vars[:]
            else:
                yield "%s)" % self.indent
            self.level -= 1

    def translate_template_line(self, data):
        literal_data = None
        if self.literal_open in data:
            data, literal_data = data.split(self.literal_open, 1)
            self.inline = True
        lstripped = data.lstrip()
        if lstripped.startswith(self.code_line_prefix):
            for line in self.string_finish():
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

    def translate_code(self, data, optimize=False):
        # Initial state
        self.inline = False # if True will skip linesep to string lines
        self.first_string_line = True
        self.unfinished_token = False

        self.base = None
        self.level = self.minlevel = 1
        self.translate_line = self.translate_template_line
        self.extends = None
        self.string_vars = []
        self.block_stack = [] # list of block levels as (base, name)
        self.block_content = collections.defaultdict()
        self.level_touched = False

        # Optimizations
        self.code_line_prefix_length = len(self.code_line_prefix)
        self.linesep_escaped = self.escape_string(self.linesep)
        self.optimize = optimize
        # Yield lines
        yield "# -*- coding: UTF-8 -*-%s" % self.linesep
        yield "def __template__():%s" % self.linesep
        for self.linenum, line in enumerate(data.splitlines()):
            for part in self.translate_line(line):
                if self.block_stack:
                    block_line, block_name = self.block_stack[-1]
                    self.block_content[block_name].append(part + self.linesep)
                    continue
                yield part + self.linesep
        for line in self.string_finish():
            yield line + self.linesep
        del self.string_vars[:]
        # Yield blocks
        yield "__parent_blocks__ = {}%s" % self.linesep
        yield "__blocks__ = {}%s" % self.linesep
        for name, lines in iteritems(self.block_content):
            yield "def __block__():%s" % self.linesep
            for line in lines:
                yield line + self.linesep
            yield "__blocks__[%r] = __block__%s" % (name, self.linesep)
        yield "__extends__ = %r%s" % (self.extends, self.linesep)


class TemplateContext(object):
    '''
    Manage context, env and evaluated function reference from given code.
    '''
    _parent = None
    _manager = None

    @property
    def extends(self):
        return self._extends

    @extends.setter
    def extends(self, name):
        self._extends = name
        if name:
            if self.manager is None:
                raise TemplateContextError("TemplateContext's extends requires manager to be passed.")
            self._parent = self.manager.get_template_context(name)
            self.parent_blocks = self._parent.blocks.copy()
            self._parent.blocks.update(self.blocks)
        else:
            self._parent = None
            self.parent_blocks.clear()

    @property
    def manager(self):
        return self._manager

    @manager.setter
    def manager(self, v):
        if self.parent:
            self.parent.manager = v
        self._manager = v

    @property
    def parent(self):
        return self._parent

    def __init__(self, code, pool, manager=None):
        self.pool = pool
        self.manager = manager
        self.namespace = {}

        self.parent_blocks = {}

        eval(code, self.namespace)
        self.template = self.namespace["__template__"]
        self.blocks = self.namespace["__blocks__"]
        self.extends = self.namespace["__extends__"]
        self.reset() # clean namespace

    def __enter__(self):
        if self.parent:
            return self.parent_context.template
        return self.template

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.reset()
        self.pool.append(self)

    def include(self, name, **environ):
        context = self.manager.get_template_context(name)
        context.update(self.namespace)
        context.update(environ)
        with context as render_func:
            for line in render_func():
                yield line

    def reset(self):
        if self.parent:
            self.parent.reset()
        self.namespace.clear()
        self.namespace.update(builtins.__dict__)
        self.namespace.update({
            # Inheritance vars
            "__include__": self.include,
            "__blocks__": self.blocks,
            "__parent_blocks__": self.parent_blocks,
            # Global functions
            "defined": self.namespace.__contains__,
            "get": self.namespace.get,
            "setdefault": self.namespace.setdefault,
            })

    def update(self, v):
        if self.parent:
            self.parent.update(v)
        self.namespace.update(v)


class Template(object):
    '''
    Template class using a template context-function pool for thread-safety.
    '''
    translate_class = CodeTranslator
    template_context_class = TemplateContext
    buffsize = 4096

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
            func = self.pool.pop()
        else:
            func = self.template_context_class(self._pycompiled, self.pool)
        if env:
            func.update(env)
        return func

    def render(self, env=None):
        with self.template_context(env) as render_func:
            buffsize = 0
            cache = []
            for line in render_func():
                buffsize += len(line)
                cache.append(line)
                if buffsize > self.buffsize:
                    yield "".join(cache)
                    buffsize = 0
                    del cache[:]
            yield "".join(cache)


class TemplateManager(object):
    template_class = Template

    def __init__(self, directories=None):
        self.directories = [] if directories is None else directories
        self.templates = {}

    def get_template_context(self, name):
        return self.templates[name].template_context()

    def render_template(self, template, env=None):
        if isinstance(template, Template):
            if not template.filename in self.templates:
                template.manager = self
                self.templates[template.filename] = template
        elif template in self.templates:
            template = self.templates[template.filename]
        else:
            with open(template) as f:
                template = Template(f.read(), template, manager=self)
                self.templates[template.filename] = template
        return template.render(env)



