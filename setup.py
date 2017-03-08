#!/usr/bin/env python
import setuptools


def get_version(filename):
    with open(filename) as in_fh:
        for line in in_fh:
            if line.startswith('__version__'):
                return line.split('=')[1].strip()[1:-1]
    raise ValueError("Cannot extract version from %s" % filename)


setuptools.setup(
    name="better-apidoc",
    version=get_version("better_apidoc.py"),
    url="https://github.com/goerz/better-apidoc",
    author="Michael Goerz",
    author_email="mail@michaelgoerz.net",
    description="A version of sphinx-apidoc with support for templating",
    install_requires=[
        'sphinx', 'jinja2'
    ],
    extras_require={'dev': ['pytest',]},
    py_modules=['better_apidoc'],
    entry_points='''
        [console_scripts]
        better-apidoc=better_apidoc:main
    ''',
    classifiers=[
        'Environment :: Console',
        'Natural Language :: English',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
)
