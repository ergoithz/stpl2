#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import unittest
import tempfile
import shutil
import os.path

from . import *

if py3k:
    xrange = range

    def to_native(text):
        return text
else:
    def to_native(text):
        return text.encode('utf-8')


class TestCodeTranslator(unittest.TestCase):
    def setUp(self):
        self.translator = CodeTranslator()

    def validate_syntax(self, code):
        pycode = ''.join(self.translator.translate_code(code))
        return compile(pycode, '<template>', 'exec')

    def testCompilation(self):
        self.validate_syntax('''
            <ul>
                % for i in range(10):
                <li>{{ i }}</li>
                % end
            </ul>
            '''.strip())

    def testInlinePass(self):
        self.validate_syntax('''
            % if False: # comment

            % elif '#':
            % elif False:

            % end
            % if True:
            % end
            '''.strip())

    def testExceptions(self):
        # Expects one argument
        templates = ("% extends", "% include", "% block", "% rebase")
        for code in templates:
            generator = self.translator.translate_code(code)
            self.assertRaises(TemplateValueError, "".join, generator)
        templates = ("% end", "% block a\n% extends test\n% end",
                     "% if True:\n% extends test\n% end",
                     "% extends 1\n% extends 2", "% block.super",
                     )
        # Block limitations
        for code in templates:
            generator = self.translator.translate_code(code)
            self.assertRaises(TemplateSyntaxError, "".join, generator)

    def testTokenParams(self):
        args = CodeTranslator.token_params('(1, 2, 3, 4, k=1, w=2)', 3)
        self.assertEqual(args, (['1','2','3'], {}, '4, k=1, w=2'))
        args = CodeTranslator.token_params('this is \'just a \\\' test\'', 3)
        self.assertEqual(args, (['this', 'is', 'just a \' test'], {}, ''))
        args = CodeTranslator.token_params('(mixed, key=value, params)', 3)
        self.assertEqual(args, (['mixed', 'params'], {'key':'value'}, ''))


class TestTemplateBase(unittest.TestCase):
    template_class = None
    def iexecute(self, code, env=None):
        return self.template_class(code).render(env)

    def execute(self, code, env=None):
        return ''.join(self.iexecute(code, env))


class TestTemplate(TestTemplateBase):
    template_class = Template
    def testNamespace(self):
        data = self.execute('''
            {{ var1 }}
            {{ get('var2', 2) }}
            {{ "hello %s" % "world" }}
            {{ var1 }} and {{ var1 }}
            <ul>
                % for i in range(10):
                <li>{{ i }}</li>
                % end
            </ul>
            <%
                a = sum(range(100))
                a //= 2
            %>
            a<%
            %>b
            <% pass %>
            <% pass %>
            a<% pass %>
            <% pass %>b
            a<% pass %>b
            <%# Comment %>
            <% \'''
            Multiline comment
            \'''%>
            a<% yield 'b' %>c
            a{{ a }}b
            100%
            ''', {'var1':1})
        indent = '            ' # Expected indent
        data = [to_native(i) for i in data.splitlines()]
        self.assertEqual(
            data,
           ['',
            indent+'1',
            indent+'2',
            indent+'hello world',
            indent+'1 and 1',
            indent+'<ul>',
           ] + [indent+'    <li>%d</li>' % i for i in xrange(10)] + [
            indent+'</ul>',
            indent+'ab',
            indent+'a',
            indent+'b',
            indent+'ab',
            indent+'abc',
            indent+'a2475b',
            indent+'100%',
            indent])

    def testExceptions(self):
        code = "% extends something"
        self.assertRaises(TemplateContextError, self.execute, code)


class TestBufferingTemplate(TestTemplateBase):
    template_class = BufferingTemplate
    def testBuffering(self):
        buffersize = self.template_class.buffersize
        data = self.iexecute(
            "ab" * int(buffersize) + "\n" +
            "c" * int(buffersize) + "\n"
            )
        self.assertEqual(len(next(data)), buffersize)
        self.assertEqual(len(next(data)), buffersize)
        self.assertEqual(len(next(data)), buffersize)
        self.assertEqual(len(next(data)), 2) # linesep excess
        self.assertRaises(StopIteration, next, data)


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = TemplateManager(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def execute(self, name, env=None):
        return ''.join(self.manager.render(name, env))

    def lines(self, name, env=None):
        data = self.execute(name, env)
        return [to_native(i).strip() for i in data.splitlines()]

    def testExtends(self):
        self.manager.templates['base1'] = Template('''
            This is base1
            % block block1
            This is base1 block1
            % end
            Interblocking
            % block block2
            This is base1 block2
            % end
            ''', manager=self.manager)
        self.manager.templates['base2'] = Template('''
            % extends base1
            This is base2
            % block block1
            This is base2 block1
            % end
            ''', manager=self.manager)
        self.manager.templates['template'] = Template('''
            % extends(name=base2)
            This is template
            % block block1
            This is template block
            % end

            Lines outside blocks are ignored on extending.

            % block "block2"
            % block.super
            {{ block.super }}
            but I am inheriting
            % end
            ''',  manager=self.manager)
        self.assertEqual(self.lines('template'),
            ['',
             'This is base1',
             'This is template block',
             'Interblocking',
             'This is base1 block2',
             'This is base1 block2',
             '',
             'but I am inheriting',
             ''])

    def testInclude(self):
        # Token
        self.manager.templates['external'] = Template('''
            External template
            ''', manager=self.manager)
        self.manager.templates['template'] = Template('''
            First line
            % include external
            Third line
            ''', manager=self.manager)
        self.assertEqual(self.lines('template'),
            ['', 'First line', '', 'External template', 'Third line', ''])
        # Variable
        self.manager.templates['external'] = Template('''
            External template
            ''', manager=self.manager)
        self.manager.templates['template'] = Template('''
            First line
            {{ include("external") }}
            Third line
            ''', manager=self.manager)
        self.assertEqual(self.lines('template'),
            ['', 'First line', '', 'External template', '',  'Third line', ''])

    def testRebase(self):
        # Token
        self.manager.templates['template'] = Template('''
            % rebase rebase
            Base template
            ''', manager=self.manager)
        self.manager.templates['rebase'] = Template('''
            First line
            % base
            Third line
            ''', manager=self.manager)
        self.assertEqual(self.lines('template'),
            ['', 'First line', '', 'Base template', 'Third line', ''])
        # Variable
        self.manager.templates['template'] = Template('''
            % rebase rebase
            Base template
            ''', manager=self.manager)
        self.manager.templates['rebase'] = Template('''
            First line
            {{ base }}
            Third line
            ''', manager=self.manager)
        self.assertEqual(self.lines('template'),
            ['', 'First line', '', 'Base template', '', 'Third line', ''])

    def testLookup(self):
        with open(os.path.join(self.tmpdir, "testmplate.stpl"), "w") as f:
            f.write('''
                Simple template
                ''')
        self.assertEqual(self.execute("testmplate").strip(), "Simple template")

    def testExceptions(self):
        self.assertRaises(TemplateNotFoundError, self.manager.get_template, "notexistent")
        self.manager.templates['a'] = Template("something", manager=self.manager)
        self.assertEqual(self.execute('a'), "something")
        self.manager.reset()
        self.assertRaises(TemplateNotFoundError, self.manager.get_template, "a")


if __name__ == '__main__':
    unittest.main()
