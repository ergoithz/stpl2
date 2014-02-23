#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import unittest

from . import Template, CodeTranslator


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.translator = CodeTranslator()

    def validate_syntax(self, code):
        pycode = "".join(self.translator.translate_code(code))
        return compile(pycode, "test.py", "exec")

    def execute(self, code, env=None):
        for pack in Template(code).render(env):
            for line in pack.splitlines():
                yield line

    def tearDown(self):
        pass

    def testCompilation(self):
        self.validate_syntax('''
            <ul>
                % for i in xrange(10):
                <li>{{ i }}</li>
                % end
            </ul>
            '''.strip())

    def testNamespace(self):
        indent = "            "
        data = self.execute('''
            {{ var1 }}
            {{ get("var2", 2) }}
            <ul>
                % for i in xrange(10):
                <li>{{ i }}</li>
                % end
            </ul>
            <%
                a = sum(xrange(100))
                a /= 2
            %>
            a<% pass %>
            <% pass %>b
            a<% pass %>b
            {{ a }}
            ''', {"var1":1})
        data = list(data)
        print data
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
            indent+"2475",
            indent])

    def testSyntax(self):
        self.validate_syntax('''
            % if False: # comment

            % elif "#":

            % end
            '''.strip())


if __name__ == "__main__":
    unittest.main()
