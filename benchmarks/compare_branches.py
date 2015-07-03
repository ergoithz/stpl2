

import timeit
import subprocess
import sys
import os.path

sys.path.insert(0, '..')
import stpl2
import stpl2.internal

def iter_branch_modules():
    initial = 'master'
    for branch in subprocess.check_output(('git', 'branch')).splitlines():
        if branch.strip():
            branch = branch.strip()
            if branch.startswith('* '):
                branch = branch[2:]
                initial = branch
            subprocess.check_output(('git', 'checkout', branch))
            reload(stpl2.internal)
            reload(stpl2)
            yield stpl2
    subprocess.check_output(('git', 'checkout', initial))

def get_manager(module):
    manager = module.TemplateManager()
    manager.templates.update({
        'base': module.Template('''
            % # Comment
            % for i in range(number):
                {{ i }}
            % end
            % block block1
                Original block1 content
            % end
            % block block2
                Original block2 content
            % end
            % block block3
                Original block2 content
            % end
            ''', manager=manager),
        'template': module.Template('''
            % extends base
            % block block1
                My block content. {{ block.super }}
            % end
            % block block2
            % end
            ''', manager=manager),
        })
    return manager


def render(render):
    return ''.join(render('template', {'number': 10}))

if __name__ == '__main__':
    for module in iter_branch_modules():
        manager = get_manager(module)
        print(timeit.timeit(lambda: render(manager.render), number=10000))
