#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import unittest

from . import *

if py3k:
    xrange = range

    def to_native(text):
        return text
else:
    def to_native(text):
        return text.encode("utf-8")


class TestTemplate(unittest.TestCase):
    def setUp(self):
        self.translator = CodeTranslator()

    def validate_syntax(self, code):
        pycode = "".join(self.translator.translate_code(code))
        return compile(pycode, "test.py", "exec")

    def execute(self, code, env=None):
        template = Template(code)
        return "".join(template.render(env))

    def tearDown(self):
        pass

    def testCompilation(self):
        self.validate_syntax('''
            <ul>
                % for i in range(10):
                <li>{{ i }}</li>
                % end
            </ul>
            '''.strip())

    def testNamespace(self):
        data = self.execute('''
            {{ var1 }}
            {{ get("var2", 2) }}
            <ul>
                % for i in range(10):
                <li>{{ i }}</li>
                % end
            </ul>
            <%
                a = sum(range(100))
                a = int(a/2)
            %>
            <% pass %>
            <% pass %>
            a<% pass %>
            <% pass %>b
            a<% pass %>b
            <%# Comment %>
            <% """
            Multiline comment
            """%>
            a<% yield "b" %>c
            a{{ a }}b
            100%
            ''', {"var1":1})
        indent = "            " # Expected indent
        data = [to_native(i) for i in data.splitlines()]
        self.assertEqual(
            data,
           ["",
            indent+"1",
            indent+"2",
            indent+"<ul>",
           ] + [indent+"    <li>%d</li>" % i for i in xrange(10)] + [
            indent+"</ul>",
            indent+"a",
            indent+"b",
            indent+"ab",
            indent+"abc",
            indent+"a2475b",
            indent+"100%",
            indent])

    def testInlinePass(self):
        self.validate_syntax('''
            % if False: # comment

            % elif "#":

            % end
            '''.strip())


class TestTemplateManager(unittest.TestCase):
    def setUp(self):
        self.manager = TemplateManager()

    def tearDown(self):
        pass

    def execute(self, name, env=None):
        template = self.manager.get_template(name)
        return "".join(template.render(env))

    def testExtends(self):
        self.manager.templates["base1"] = Template('''
            This is base1
            % block block1
            This is base1 block1
            % end
            Interblocking
            % block block2
            This is base1 block2
            % end
            ''', manager=self.manager)
        self.manager.templates["base2"] = Template('''
            % extends base1
            This is base2
            % block block1
            This is base2 block1
            % end
            ''', manager=self.manager)
        self.manager.templates["template"] = Template('''
            % extends base2
            This is template
            % block block1
            This is template block
            % end

            Lines outside blocks are ignored on extending.

            % block block2
            % block.super
            but I am inheriting
            % end
            ''',  manager=self.manager)
        data = self.execute("template")
        data = [to_native(i).strip() for i in data.splitlines()]
        self.assertEqual(
            data,
            ["",
             "This is base1",
             "This is template block",
             "Interblocking",
             "This is base1 block2",
             "but I am inheriting",
             ""])

    def testInclude(self):
        self.manager.templates["external"] = Template('''
            External template
            ''', manager=self.manager)
        self.manager.templates["template"] = Template('''
            First line
            % include external
            Third line
            ''', manager=self.manager)
        data = self.execute("template")
        data = [to_native(i).strip() for i in data.splitlines()]
        self.assertEqual(
            data,
            ["",
             "First line",
             "",
             "External template",
             "",
             "Third line",
             ""])



if __name__ == "__main__":
    unittest.main()
