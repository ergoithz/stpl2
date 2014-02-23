#!/usr/bin/env python
# -*- coding: UTF-8 -*-


import re
import collections
import __builtin__ as builtin


class TemplateSyntaxError(SyntaxError):
    pass


class TemplateContextError(ValueError):
    pass


class CodeTranslator(object):
    '''
    Translate from SimpleTemplateLanguage to Python code.

    Lines starting with % are evaluated as inline code

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
    custom_tokens = {"block", "end", "extends", "include"}

    def __init__(self):
        # Compile regexps
        rb = "(?P<%s>(^%s(\s|\(|$)))"
        rj = "(\s|\(|$))|(^".join
        self.re_tokens = re.compile("|".join((
            rb % ("indent", rj(self.indent_tokens)),
            rb % ("redent", rj(self.redent_tokens)),
            rb % ("custom", rj(self.custom_tokens)),
            )))
        self.re_var = re.compile("%s(.*)%s" % (self.variable_open, self.variable_close))

    def re_var_sub(self, match):
        self.string_vars.append(match.groups()[0])
        return "%s"

    def parse_token_params(self, params):
        if params.startswith("(") and params.endswith(")"):
            args = params.split("=", 1)[0].rsplit(",")[0][1:]
            kwargs =    1
            args = eval(")")

    def parse_token(self, line):
        '''
        Parses custom token.

        :param basestring line: line containing token
        :return tuple: tuple as (token, argument tuple, keyword argument dict).
        '''
        line = line.strip()
        sep = len(line)
        for i in "( ":
            index = line.find(i)
            if -1 < index < sep:
                sep = index
        args, kwargs = self.parse_token_params(line[sep:])
        return line[:sep], args, kwargs

    @property
    def indent(self):
        return self.tab * self.level

    def translate_code_line(self, data):
        # Code line
        lstripped = data[self.code_line_prefix_length:].lstrip()
        group = self.re_tokens.match(lstripped).groupdict()
        if group["custom"]:
            token = group["custom"]
            if token == "end":
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
            elif token == "extends":
                # extends is managed by template context
                if self.level > self.minlevel:
                    raise TemplateSyntaxError("Token 'extends' must be outside any block (line %d)." % self.linenum)
                elif not self.extends is None:
                    raise TemplateSyntaxError("Token 'extends' cannot be defined twice (line %d)." % self.linenum)
                name = lstripped.split(" ", 1)[1].strip()
                self.extends = self.strip_str(name)
            elif token == "block":
                # yield from block
                name = lstripped.split(" ", 1)[1].strip()
                yield self.indent + "for line in __blocks__[%r]():" % name
                self.level += 1
                yield self.indent + "yield line"
                # start putting lines on new block
                self.block_stack.append((self.level, name))
                self.level = self.minlevel
                self.level_touched = False
            elif token == "include":
                yield
        elif group["redent"]:
            if not self.level_touched:
                yield self.indent + "pass"
            self.level -= 1
            yield self.indent + lstripped
            self.level += 1
            self.level_touched = False
        else:
            if lstripped.strip():
                yield self.indent + lstripped
            if group["indent"]:
                self.level += 1
                self.level_touched = False

    def translate_string_line(self, data):
        # Template line
        self.level_touched = True
        if data.strip():
            data = self.re_var.sub(self.re_var_sub, data).encode("string-escape")
            trail = "" if self.inline else self.linesep_escaped
            if self.string_vars:
                tuple_indent = self.tab * (self.level + len(data) + 4)
                sep = ",%s%s" % (self.linesep, tuple_indent)
                extra = " %% (%s)" % sep.join(self.string_vars)
                del self.string_vars[:] # clear
            else:
                extra = ""
            yield "%syield \"%s%s\"%s" % (self.indent, data, trail, extra)
        elif not self.inline:
            yield "%syield \"%s%s\"" % (self.indent, data, self.linesep_escaped)

    def translate_literal_line(self, data):
        template_data = None
        if self.literal_close in data:
            data, template_data = data.split(self.literal_close, 1)
        if data.strip():
            if self.base is None:
                self.base = len(data) - len(data.lstrip())
            yield self.indent + data[self.base:]
        else:
            # Empty lines for text literals
            yield ""
        if not template_data is None:
            # Reset
            self.base = None
            self.inline = False
            # Switch to template mode
            self.translate_line = self.translate_template_line
            if template_data.strip():
                yield "%syield \"%s\"" % (self.indent, " " * self.previous_indent)
                for line in self.translate_line(template_data):
                    yield line
            elif self.previous_code:
                yield "%syield \"%s\"" % (self.indent, self.linesep_escaped)

    def translate_template_line(self, data):
        literal_data = None
        if self.literal_open in data:
            data, literal_data = data.split(self.literal_open, 1)
            self.inline = True
        lstripped = data.lstrip()
        if lstripped.startswith(self.code_line_prefix):
            self.previous_code = False
            for line in self.translate_code_line(lstripped):
                yield line
        else:
            if self.inline:
                if data.strip():
                    self.previous_code = True
                    self.previous_indent = 0
                else:
                    self.previous_code = False
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
        self.linesep_escaped = self.linesep.encode("string-escape")
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
        # Yield blocks
        yield "__blocks__ = {}%s" % self.linesep
        for name, lines in self.block_content.iteritems():
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
            self._parent.blocks.update(self.blocks)
        else:
            self._parent = None

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
        self.namespace.update(builtin.__dict__)
        self.namespace.update({
            "__blocks__": self.blocks,
            "__include__": self.include,
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
        self._code = v
        self._pycode = "".join(self.translate_class().translate_code(v))
        print self._pycode
        self._pycompiled = compile(self._pycode, self.filename or "<template>", "exec")

    @property
    def pycode(self):
        return self._pycode

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



