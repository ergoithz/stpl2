#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import unittest

from . import Template, CodeTranslator, builtins

if not hasattr(builtins, "xrange"):
    xrange = range

class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.translator = CodeTranslator()

    def validate_syntax(self, code):
        pycode = "".join(self.translator.translate_code(code))
        return compile(pycode, "test.py", "exec")

    def execute(self, code, env=None):
        template = Template(code)
        print(template.pycode)
        for pack in template.render(env):
            for line in pack.splitlines():
                yield line

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
        indent = "            "
        data = list(self.execute('''
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
            ''', {"var1":1}))
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

    def testSyntax(self):
        self.validate_syntax('''
            % if False: # comment

            % elif "#":

            % end
            '''.strip())


if __name__ == "__main__":
    unittest.main()
