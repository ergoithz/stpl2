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
    manager.render("my_template", {"some":1,"vars":2}

my_template.tpl

    This is sort of template.
    With {{ some }} {{ vars }}.




'''
import re
import sys
import zlib
import collections
import os
import os.path

# Py3k fixes
py3k = sys.version > '3'
if py3k:
    import builtins
    iteritems = dict.items
    unicode_prefix = ''
    base_notfounderror = FileNotFoundError
    yield_from_supported = sys.version_info.minor > 2
    maxint = sys.maxsize
    native_string_bases = (str,)

    def escape_string(data):
        return data.encode('unicode_escape').decode('ascii')
else:
    import __builtin__ as builtins
    iteritems = dict.iteritems
    unicode_prefix = 'u'
    base_notfounderror = IOError
    yield_from_supported = False
    maxint = sys.maxint
    native_string_bases = (basestring,)

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
    '''
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
                yield "%s) %% (%s)" % (self.indent, ",".join(self.string_vars))
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
        self.string_vars.append(match.groups()[0])
        return "%s"

    def translate_token_end(self, params=None):
        '''
        Decrement current indentation level.
        :yield str: line pass if current block is empty
        '''
        if not self.level_touched:
            yield "%spass" % self.indent
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
            raise TemplateValueError("Token 'extends' receives at least one argument: name (line %d)." % self.linenum)
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
            raise TemplateValueError("Token 'block' receives at least one argument: name (line %d)." % self.linenum)
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
            raise TemplateValueError("Token 'include' receives at least one argument: name (line %d)." % self.linenum)
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
            raise TemplateValueError("Token 'rebase' receives at least one argument: name (line %d)." % self.linenum)
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
                yield '%spass' % self.indent
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
        :yields: lines that's starts yielding string (if not already done) and string line.
        '''
        # String
        if data.strip():
            data = self.re_var.sub(self.translate_var, data.replace("%", "%%"))
            data = escape_string(data)
            for i in self.yield_string_start():
                yield i
            yield "%s%s\"%s\"" % (self.indent, unicode_prefix, data)
        elif not self.inline:
            data = escape_string(data)
            for i in self.yield_string_start():
                yield i
            yield "%s%s\"%s\"" % (self.indent, unicode_prefix, data)

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
        oneline = False
        for self.linenum, line in enumerate(data.splitlines(True)):
            for part in self.translate_line(line):
                if self.block_stack:
                    block_line, block_name = self.block_stack[-1]
                    self.block_content[block_name].append(part)
                    continue
                oneline |= True
                yield part + self.linesep
        self.level = self.minlevel # Reset level
        if not oneline:
            # empty template, pass
            yield "%spass%s" % (self.indent, self.linesep)
        else:
            for line in self.yield_string_finish():
                yield line + self.linesep
            del self.string_vars[:]
        # Yield blocks
        yield "__blocks__ = {}%s" % self.linesep
        for name, lines in iteritems(self.block_content):
            yield "def __block__(block):%s" % self.linesep
            oneline = False
            for linenum, line in enumerate(lines):
                oneline |= True
                yield line + self.linesep
            if not oneline:
                yield "%spass%s" % (self.indent, self.linesep)
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
    @classmethod
    def _none(self):
        return ()

    def __init__(self, iterfunc=None, *args, **kwargs):
        self._iterfunc = self._none if iterfunc is None else iterfunc
        self._args = args
        self._kwargs = kwargs

    def __iter__(self):
        for line in self._iterfunc(*self._args, **self._kwargs):
            yield line

    def __str__(self):
        return "".join(self)


class LocalBlockGenerator(StringGenerator):
    '''
    Block context variable inside blocks
    '''
    def __init__(self, superfunc, *args, **kwargs):
        StringGenerator.__init__(self)
        self.super = StringGenerator(superfunc, *args, **kwargs)


class BlockGenerator(StringGenerator):
    '''
    Object retrieved by block function
    '''
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
        for line in self._iterfunc(local_block):
            yield line


class TemplateContext(object):
    '''
    Template namespace boilerplate, interpret, manages context, inheritance and
    generator functions from given template code.

    Can be used as context manager.
    '''
    block_class = BlockGenerator
    base_class = StringGenerator
    include_class = StringGenerator

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
        self.includes_cache = {}

        # Relations for rebase
        self.rebased = None
        self.base = ""

        # Relations for extends
        self.parent = None
        self.child = None

        eval(code, self.namespace)
        self.owned_template = self.namespace["__template__"]

        self.blocks = self.namespace["__blocks__"]
        self.includes = self.namespace["__includes__"]

        self.extends = self.namespace["__extends__"]
        self.rebase = self.namespace["__rebase__"]

        if self.manager is None and (self.includes or self.extends or self.rebase):
            raise TemplateContextError("TemplateContext's extends, include and rebase require a template manager.")

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
            self.rebased.base = self.get_base()

        self.reset() # clean namespace

    def __enter__(self):
        return self.template

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.reset()
        self.pool.append(self)

    def get_include(self, name, **environ):
        '''
        Get include iterable based on :py:cvar:include_class
        '''
        if not name in self.includes_cache:
            self.includes_cache[name] = self.manager.get_template(name).get_context()
        context = self.includes_cache[name]
        context.reset()
        context.update(environ)
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
            context.reset()
            context.update(environ)
            return context.block_class(context.blocks[name], context.iter_super, name)

    def get_base(self, **environ):
        '''
        Get block iterable based on :py:cvar:block_base
        '''
        return self.base_class(self.base_template)

    def iter_super(self, name, local_block_class, **environ):
        '''
        Get nearest parent block generator with given name
        '''
        context = None
        for parent in self.iter_ancestors():
            if name in parent.blocks:
                context = parent
                break
        if context:
            context.reset()
            context.update(environ)
            return context.blocks[name](local_block_class)
        return ()

    def reset(self):
        '''
        Clears and repopulate template namespace
        '''
        if self.rebased:
            self.rebased.reset()
        self.namespace.clear()
        self.namespace.update(builtins.__dict__)
        self.namespace.update({
            # Global vars
            "base": self.base,
            # Global functions
            "include": self.get_include,
            "block": self.get_block,
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

    @property
    def pycode(self):
        return zlib.decompress(self._pycode).decode("utf-8")

    @property
    def manager(self):
        return self._manager

    @property
    def filename(self):
        return self._filename

    def __init__(self, code, filename=None, manager=None):
        self._filename = filename
        self._manager = manager

        pycode = "".join(self.translate_class().translate_code(code))
        self._code = code
        self._pycode = zlib.compress(pycode.encode("utf-8"))
        self._pycompiled = compile(pycode, filename or "<template>", "exec")
        self._pool = []

    def get_context(self, env=None):
        '''
        Generate the new template generator function
        '''
        if self._pool:
            context = self._pool.pop()
        else:
            context = self.template_context_class(self._pycompiled, self._pool, self._manager)
        if env:
            context.update(env)
        return context

    def render(self, env=None):
        '''
        Renders template updating global namespace with env dict-like object.

        :param dict env: environment dictionary
        :yields str: template lines as string
        '''
        with self.get_context(env) as render_func:
            for line in render_func():
                yield line


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
    template_extensions = (".tpl", ".stpl")

    def __init__(self, directories=None):
        self.directories = ensure_set(directories)
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
                raise TemplateNotFoundError("Template %r not found" % name)
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
        template = self.get_template(name)
        for line in template.render(env):
            yield line

    def reset(self):
        '''
        Clear template cache.
        '''
        self.templates.clear()


def ensure_set(obj):
    '''
    Ensure given object is correctly converted to a set.

    :param obj: any python object
    :return: set containing obj or elements from obj if non-string iterable.
    '''
    if obj is None:
        return set()
    elif isinstance(obj, native_string_bases):
        return set((obj,))
    elif not isinstance(obj, set):
        return set(obj)
    return obj