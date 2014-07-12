# -*- coding: utf-8 -*-
"""
Stpl2
========

Stpl2 (formerly SimpleTemplate Engine 2) is a reimplementation
of bottle.py SimpleTemplate Engine templating system focused on
code quality, maintenability and documentation, and it's aimed
to generate high-quality and fast python code from templates.

More details on the `github page <https://github.com/ergoithz/stpl2/>`_.


Development Version
-------------------

The Stpl2 development version can be installed by cloning the git
repository from `github`_::

    git clone git@github.com:ergoithz/stpl2.git

.. _github: https://github.com/ergoithz/stpl2
"""
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(
    name='stpl2',
    version='0.2',
    url='https://github.com/ergoithz/stpl2',
    download_url = 'https://github.com/ergoithz/stpl2/tarball/0.2',
    license='MIT',
    author='Felipe A. Hernandez',
    author_email='ergoithz@gmail.com',
    description='Fast and pythonic template engine',
    long_description=__doc__,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    keywords = ['template', 'engine'],
    packages=['stpl2'],
    include_package_data=True,
    test_suite='stpl2.tests',
    zip_safe=False,
    platforms='any'
)
