# -*- coding: utf-8 -*-
"""
    better apidoc
    ~~~~~~~~~~~~~

    Parses a directory tree looking for Python modules and packages and creates
    ReST files appropriately to create code documentation with Sphinx.  It also
    creates a modules index (named modules.<suffix>).

    This is derived from the "sphinx-apidoc" script, which is:
    Copyright 2007-2016 by the Sphinx team
    http://www.sphinx-doc.org

    It extends "sphinx-apidoc" by the --template / -t option, which allows to
    render the output ReST files based on arbitrary Jinja templates.

    :copyright: Copyright 2017-2018 by Michael Goerz
    :license: BSD, see LICENSE for details.
"""
from __future__ import print_function

import os
import sys
import re
import inspect
import importlib
import optparse
from os import path
from functools import partial
from six import binary_type
from fnmatch import fnmatch
from docutils import nodes
from docutils.parsers.rst.states import RSTStateMachine, state_classes
from docutils.utils import new_document, Reporter as NullReporter

from jinja2 import FileSystemLoader, TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment

from sphinx.util.osutil import FileAvoidWrite, walk
#from sphinx import __display_version__
try:
    from sphinx.cmd.quickstart import EXTENSIONS
except ImportError:
    from sphinx.quickstart import EXTENSIONS
from sphinx.ext.autosummary import get_documenter
from sphinx.util.inspect import safe_getattr

# App must be set before calling main()
APP = None

periods_re = re.compile(r'\.(?:\s+)')

__version__ = '0.3.1'
__display_version__ = __version__

if False:
    # For type annotation
    from typing import Any, List, Tuple  # NOQA


# automodule options
if 'SPHINX_APIDOC_OPTIONS' in os.environ:
    OPTIONS = os.environ['SPHINX_APIDOC_OPTIONS'].split(',')
else:
    OPTIONS = [
        'members',
        'undoc-members',
        # 'inherited-members', # disabled because there's a bug in sphinx
        'show-inheritance',
    ]

INITPY = '__init__.py'
PY_SUFFIXES = set(['.py', '.pyx'])


def _warn(msg):
    # type: (unicode) -> None
    print('WARNING: ' + msg, file=sys.stderr)


def makename(package, module):
    # type: (unicode, unicode) -> unicode
    """Join package and module with a dot."""
    # Both package and module can be None/empty.
    if package:
        name = package
        if module:
            name += '.' + module
    else:
        name = module
    return name


def write_file(name, text, opts):
    # type: (unicode, unicode, Any) -> None
    """Write the output file for module/package <name>."""
    fname = path.join(opts.destdir, '%s.%s' % (name, opts.suffix))
    if opts.dryrun:
        print('Would create file %s.' % fname)
        return
    if not opts.force and path.isfile(fname):
        print('File %s already exists, skipping.' % fname)
    else:
        print('Creating file %s.' % fname)
        with FileAvoidWrite(fname) as f:
            f.write(text)


def format_heading(level, text):
    # type: (int, unicode) -> unicode
    """Create a heading of <level> [1, 2 or 3 supported]."""
    underlining = ['=', '-', '~', ][level - 1] * len(text)
    return '%s\n%s\n\n' % (text, underlining)


def format_directive(module, package=None):
    # type: (unicode, unicode) -> unicode
    """Create the automodule directive and add the options."""
    directive = '.. automodule:: %s\n' % makename(package, module)
    for option in OPTIONS:
        directive += '    :%s:\n' % option
    return directive


def create_module_file(package, module, opts):
    # type: (unicode, unicode, Any) -> None
    """Generate RST for a top-level module (i.e., not part of a package)"""
    if not opts.noheadings:
        text = format_heading(1, '%s module' % module)
    else:
        text = ''
    # text += format_heading(2, ':mod:`%s` Module' % module)
    text += format_directive(module, package)

    if opts.templates:
        template_loader = FileSystemLoader(opts.templates)
        template_env = SandboxedEnvironment(loader=template_loader)
        try:
            mod_ns = _get_mod_ns(
                name=module, fullname=module,
                includeprivate=opts.includeprivate)
            template = template_env.get_template('module.rst')
            text = template.render(**mod_ns)
        except ImportError as e:
            _warn('failed to import %r: %s' % (module, e))
        add_get_members_to_template_env(template_env, module, opts)
    write_file(makename(package, module), text, opts)


def _get_documenter(app, member, mod):
    try:  # Sphinx >= 2.0
        return get_documenter(app=app, obj=member, parent=mod)
    except TypeError:  # Sphinx < 2.0 does not accept kwargs
        try:  # Sphinx 1.7, 1.8
            return get_documenter(app, member, mod)
        except (TypeError, ValueError):  # Sphinx < 1.7
            return get_documenter(member, mod)


def _get_members(
        mod, typ=None, include_imported=False, out_format='names',
        in_list=None, known_refs=None):
    """Get (filtered) public/total members of the module or package `mod`.


    Returns:
        lists `public` and `items`. The lists contains the public and private +
        public members, as strings.
    """
    roles = {'function': 'func', 'module': 'mod', 'class': 'class',
             'exception': 'exc', 'data': 'data'}
    # not included, because they cannot occur at modul level:
    #   'method': 'meth', 'attribute': 'attr', 'instanceattribute': 'attr'

    out_formats = ['names', 'fullnames', 'refs', 'table']
    if out_format not in out_formats:
        raise ValueError("out_format %s not in %r" % (out_format, out_formats))

    def check_typ(typ, mod, member):
        """Check if mod.member is of the desired typ"""
        if inspect.ismodule(member):
            return False
        documenter = _get_documenter(APP, member, mod)
        if typ is None:
            return True
        if typ == getattr(documenter, 'objtype', None):
            return True
        if hasattr(documenter, 'directivetype'):
            return roles[typ] == getattr(documenter, 'directivetype')

    def is_local(mod, member, name):
        """Check whether mod.member is defined locally in module mod"""
        if hasattr(member, '__module__'):
            return getattr(member, '__module__') == mod.__name__
        else:
            # we take missing __module__ to mean the member is a data object
            # it is recommended to filter data by e.g. __all__
            return True

    if typ is not None and typ not in roles:
        raise ValueError("typ must be None or one of %s"
                         % str(list(roles.keys())))
    items = []
    public = []
    if known_refs is None:
        known_refs = {}
    elif isinstance(known_refs, str):
        known_refs = getattr(mod, known_refs)
    if in_list is not None:
        try:
            in_list = getattr(mod, in_list)
        except AttributeError:
            in_list = []
    for name in dir(mod):
        if name.startswith('__'):
            continue
        try:
            member = safe_getattr(mod, name)
        except AttributeError:
            continue
        if check_typ(typ, mod, member):
            if in_list is not None:
                if name not in in_list:
                    continue
            if not (include_imported or is_local(mod, member, name)):
                continue
            if out_format in ['table', 'refs']:
                documenter = _get_documenter(APP, member, mod)
                role = roles.get(documenter.objtype, 'obj')
                ref = _get_member_ref_str(
                        name, obj=member, role=role,
                        known_refs=known_refs)
            if out_format == 'table':
                docsummary = extract_summary(member)
                items.append((ref, docsummary))
                if not name.startswith('_'):
                    public.append((ref, docsummary))
            elif out_format == 'refs':
                items.append(ref)
                if not name.startswith('_'):
                    public.append(ref)
            elif out_format == 'fullnames':
                fullname = _get_fullname(name, obj=member)
                items.append(fullname)
                if not name.startswith('_'):
                    public.append(fullname)
            else:
                assert out_format == 'names', str(out_format)
                items.append(name)
                if not name.startswith('_'):
                    public.append(name)
    if out_format == 'table':
        return _assemble_table(public), _assemble_table(items)
    else:
        return public, items


def _assemble_table(rows):
    if len(rows) == 0:
        return ''
    lines = []
    lines.append('.. list-table::')
    lines.append('')
    for row in rows:
        lines.append('   * - %s' % row[0])
        for col in row[1:]:
            lines.append('     - %s' % col)
    lines.append('')
    return lines


def extract_summary(obj):
    # type: (List[unicode], Any) -> unicode
    """Extract summary from docstring."""

    try:
        doc = inspect.getdoc(obj).split("\n")
    except AttributeError:
        doc = ''

    # Skip a blank lines at the top
    while doc and not doc[0].strip():
        doc.pop(0)

    # If there's a blank line, then we can assume the first sentence /
    # paragraph has ended, so anything after shouldn't be part of the
    # summary
    for i, piece in enumerate(doc):
        if not piece.strip():
            doc = doc[:i]
            break

    # Try to find the "first sentence", which may span multiple lines
    sentences = periods_re.split(" ".join(doc))  # type: ignore
    if len(sentences) == 1:
        summary = sentences[0].strip()
    else:
        summary = ''
        state_machine = RSTStateMachine(state_classes, 'Body')
        while sentences:
            summary += sentences.pop(0) + '.'
            node = new_document('')
            node.reporter = NullReporter('', 999, 4)
            node.settings.pep_references = None
            node.settings.rfc_references = None
            state_machine.run([summary], node)
            if not node.traverse(nodes.system_message):
                # considered as that splitting by period does not break inline
                # markups
                break

    return summary


def _get_member_ref_str(name, obj, role='obj', known_refs=None):
    """generate a ReST-formmated reference link to the given `obj` of type
    `role`, using `name` as the link text"""
    if known_refs is not None:
        if name in known_refs:
            return known_refs[name]
    ref = _get_fullname(name, obj)
    return ":%s:`%s <%s>`" % (role, name, ref)


def _get_fullname(name, obj):
    if hasattr(obj, '__qualname__'):
        try:
            ref = obj.__module__ + '.' + obj.__qualname__
        except AttributeError:
            ref = obj.__name__
        except TypeError:  # e.g. obj.__name__ is None
            ref = name
    elif hasattr(obj, '__name__'):
        try:
            ref = obj.__module__ + '.' + obj.__name__
        except AttributeError:
            ref = obj.__name__
        except TypeError:  # e.g. obj.__name__ is None
            ref = name
    else:
        ref = name
    return ref


def _get_mod_ns(name, fullname, includeprivate):
    """Return the template context of module identified by `fullname` as a
    dict"""
    ns = {  # template variables
        'name': name, 'fullname': fullname, 'members': [], 'functions': [],
        'classes': [], 'exceptions': [], 'subpackages': [], 'submodules': [],
        'doc': None}
    p = 0
    if includeprivate:
        p = 1
    mod = importlib.import_module(fullname)
    ns['members'] = _get_members(mod)[p]
    ns['functions'] = _get_members(mod, typ='function')[p]
    ns['classes'] = _get_members(mod, typ='class')[p]
    ns['exceptions'] = _get_members(mod, typ='exception')[p]
    ns['data'] = _get_members(mod, typ='data')[p]
    ns['doc'] = mod.__doc__
    return ns


def add_get_members_to_template_env(template_env, fullname, opts):

    def get_members(
            fullname, typ=None, include_imported=False, out_format='names',
            in_list=None, includeprivate=opts.includeprivate, known_refs=None):
        """Return a list of members

        Args:
            fullname (str): The full name of the module for which to get the
                members (including the dot-separated package path)
            typ (None or str): One of None, 'function', 'class', 'exception',
                'data'. If not None, only members of the corresponding type
                 will be returned
            include_imported (bool): If True, include members that are imported
                from other modules. If False, only return members that are
                defined directly in the module.
            out_format (str): One of 'names', 'fullnames', 'refs', and 'table'
            in_list (None or str): If not None, name of a module
                attribute (e.g. '__all__'). Only members whose names appears in
                the list will be returned.
            includeprivate (bool): If True, include members whose names starts
                with an underscore
            know_refs (None or dict or str): If not None, a mapping of names to
                rull rst-formatted references. If given as a str, the mapping
                will be taken from the module attribute of the given name. This
                is used only in conjunction with ``out_format=refs``, to
                override automatically detected reference location, or to
                provide references for object that cannot be located
                automatically (data objects).

        Returns:
            list: List of strings, depending on `out_format`.

            If 'names' (default), return a list of the simple names of all
            members.

            If 'fullnames', return a list of the fully qualified names
            of the members.

            If 'refs', return a list of rst-formatted links.

            If 'table', return a list of lines for a rst table similar to that
            generated by the autosummary plugin (left column is linked member
            names, right column is first sentence of the docstring)


        Note:
            For data members, it is not always possible to determine whther
            they are imported or defined locally. In this case, `in_list` and
            `known_refs` may be used to achieve the desired result.

            If using ``in_list='__all__'`` for a package you may also have to
            use ``include_imported=True`` to get the full list (as packages
            typically export members imported from their sub-modules)
        """
        mod = importlib.import_module(fullname)
        p = 0
        if includeprivate:
            p = 1
        members = _get_members(
            mod, typ=typ, include_imported=include_imported,
            out_format=out_format, in_list=in_list, known_refs=known_refs)[p]
        return members

    template_env.globals['get_members'] = partial(
        get_members, fullname=fullname)


def create_package_file(root, master_package, subroot, py_files, opts, subs, is_namespace):
    # type: (unicode, unicode, unicode, List[unicode], Any, List[unicode], bool) -> None
    """Build the text of the file and write the file."""

    use_templates = False
    fullname = makename(master_package, subroot)

    if opts.templates:
        use_templates = True
        template_loader = FileSystemLoader(opts.templates)
        template_env = SandboxedEnvironment(loader=template_loader)

    text = format_heading(
        1, ('%s package' if not is_namespace else "%s namespace") % fullname)

    if opts.modulefirst and not is_namespace:
        text += format_directive(subroot, master_package)
        text += '\n'

    # build a list of directories that are szvpackages (contain an INITPY file)
    subs = [sub for sub in subs if path.isfile(path.join(root, sub, INITPY))]
    # if there are some package directories, add a TOC for theses subpackages
    if subs:
        text += format_heading(2, 'Subpackages')
        text += '.. toctree::\n\n'
        for sub in subs:
            text += '    %s.%s\n' % (makename(master_package, subroot), sub)
        text += '\n'

    submods = [path.splitext(sub)[0] for sub in py_files
               if not shall_skip(path.join(root, sub), opts) and
               sub != INITPY]

    if use_templates:
        try:
            package_ns = _get_mod_ns(name=subroot, fullname=fullname,
                                     includeprivate=opts.includeprivate)
            package_ns['subpackages'] = subs
            package_ns['submodules'] = submods
        except ImportError as e:
            _warn('failed to import %r: %s' % (fullname, e))

    if submods:
        text += format_heading(2, 'Submodules')
        if opts.separatemodules:
            text += '.. toctree::\n\n'
            for submod in submods:
                modfile = makename(master_package, makename(subroot, submod))
                text += '   %s\n' % modfile

                # generate separate file for this module
                if not opts.noheadings:
                    filetext = format_heading(1, '%s module' % modfile)
                else:
                    filetext = ''
                filetext += format_directive(makename(subroot, submod),
                                             master_package)
                if use_templates:
                    try:
                        mod_ns = _get_mod_ns(
                            name=submod, fullname=modfile,
                            includeprivate=opts.includeprivate)
                        template = template_env.get_template('module.rst')
                        add_get_members_to_template_env(
                            template_env, modfile, opts)
                        filetext = template.render(**mod_ns)
                    except ImportError as e:
                        _warn('failed to import %r: %s' % (modfile, e))
                write_file(modfile, filetext, opts)
        else:
            for submod in submods:
                modfile = makename(master_package, makename(subroot, submod))
                if not opts.noheadings:
                    text += format_heading(2, '%s module' % modfile)
                text += format_directive(makename(subroot, submod),
                                         master_package)
                text += '\n'
        text += '\n'

    if use_templates:
        template = template_env.get_template('package.rst')
        add_get_members_to_template_env(template_env, fullname, opts)
        text = template.render(**package_ns)
    else:
        if not opts.modulefirst and not is_namespace:
            text += format_heading(2, 'Module contents')
            text += format_directive(subroot, master_package)

    write_file(makename(master_package, subroot), text, opts)


def create_modules_toc_file(modules, opts, name='modules'):
    # type: (List[unicode], Any, unicode) -> None
    """Create the module's index."""
    text = format_heading(1, '%s' % opts.header)
    text += '.. toctree::\n'
    text += '   :maxdepth: %s\n\n' % opts.maxdepth

    modules.sort()
    prev_module = ''  # type: unicode
    for module in modules:
        # look if the module is a subpackage and, if yes, ignore it
        if module.startswith(prev_module + '.'):
            continue
        prev_module = module
        text += '   %s\n' % module

    write_file(name, text, opts)


def shall_skip(module, opts):
    # type: (unicode, Any) -> bool
    """Check if we want to skip this module."""
    # skip if the file doesn't exist and not using implicit namespaces
    if not opts.implicit_namespaces and not path.exists(module):
        return True

    # skip it if there is nothing (or just \n or \r\n) in the file
    if path.exists(module) and path.getsize(module) <= 2:
        return True

    # skip if it has a "private" name and this is selected
    filename = path.basename(module)
    if filename != '__init__.py' and filename.startswith('_') and \
       not opts.includeprivate:
        return True
    return False


def recurse_tree(rootpath, excludes, opts):
    # type: (unicode, List[unicode], Any) -> List[unicode]
    """
    Look for every file in the directory tree and create the corresponding
    ReST files.
    """
    # check if the base directory is a package and get its name
    if INITPY in os.listdir(rootpath):
        root_package = rootpath.split(path.sep)[-1]
    else:
        # otherwise, the base is a directory with packages
        root_package = None

    toplevels = []
    followlinks = getattr(opts, 'followlinks', False)
    includeprivate = getattr(opts, 'includeprivate', False)
    implicit_namespaces = getattr(opts, 'implicit_namespaces', False)
    for root, subs, files in walk(rootpath, followlinks=followlinks):
        # document only Python module files (that aren't excluded)
        py_files = sorted(f for f in files
                          if path.splitext(f)[1] in PY_SUFFIXES and
                          not is_excluded(path.join(root, f), excludes))
        is_pkg = INITPY in py_files
        is_namespace = INITPY not in py_files and implicit_namespaces
        if is_pkg:
            py_files.remove(INITPY)
            py_files.insert(0, INITPY)
        elif root != rootpath:
            # only accept non-package at toplevel unless using implicit namespaces
            if not implicit_namespaces:
                del subs[:]
                continue
        # remove hidden ('.') and private ('_') directories, as well as
        # excluded dirs
        if includeprivate:
            exclude_prefixes = ('.',)  # type: Tuple[unicode, ...]
        else:
            exclude_prefixes = ('.', '_')
        subs[:] = sorted(sub for sub in subs if not sub.startswith(exclude_prefixes) and
                         not is_excluded(path.join(root, sub), excludes))

        if is_pkg or is_namespace:
            # we are in a package with something to document
            if subs or len(py_files) > 1 or not shall_skip(path.join(root, INITPY), opts):
                subpackage = root[len(rootpath):].lstrip(path.sep).\
                    replace(path.sep, '.')
                # if this is not a namespace or
                # a namespace and there is something there to document
                if not is_namespace or len(py_files) > 0:
                    create_package_file(root, root_package, subpackage,
                                        py_files, opts, subs, is_namespace)
                    toplevels.append(makename(root_package, subpackage))
        else:
            # if we are at the root level, we don't require it to be a package
            assert root == rootpath and root_package is None
            if opts.templates:
                sys.path.insert(0, rootpath)
            for py_file in py_files:
                if not shall_skip(path.join(rootpath, py_file), opts):
                    module = path.splitext(py_file)[0]
                    create_module_file(root_package, module, opts)
                    toplevels.append(module)
            if opts.templates:
                sys.path.pop(0)

    return toplevels


def normalize_excludes(rootpath, excludes):
    # type: (unicode, List[unicode]) -> List[unicode]
    """Normalize the excluded directory list."""
    return [path.abspath(exclude) for exclude in excludes]


def is_excluded(root, excludes):
    # type: (unicode, List[unicode]) -> bool
    """Check if the directory is in the exclude list.

    Note: by having trailing slashes, we avoid common prefix issues, like
          e.g. an exlude "foo" also accidentally excluding "foobar".
    """
    for exclude in excludes:
        if fnmatch(root, exclude):
            return True
    return False


def main(argv=sys.argv):
    # type: (List[str]) -> int
    """Parse and check the command line arguments."""
    parser = optparse.OptionParser(
        usage="""\
usage: %prog [options] -o <output_path> <module_path> [exclude_pattern, ...]

Look recursively in <module_path> for Python modules and packages and create
one reST file with automodule directives per package in the <output_path>.

The <exclude_pattern>s can be file and/or directory patterns that will be
excluded from generation.

Note: By default this script will not overwrite already created files.""")

    parser.add_option('-o', '--output-dir', action='store', dest='destdir',
                      help='Directory to place all output', default='')
    parser.add_option('-d', '--maxdepth', action='store', dest='maxdepth',
                      help='Maximum depth of submodules to show in the TOC '
                      '(default: 4)', type='int', default=4)
    parser.add_option('-f', '--force', action='store_true', dest='force',
                      help='Overwrite existing files')
    parser.add_option('-l', '--follow-links', action='store_true',
                      dest='followlinks', default=False,
                      help='Follow symbolic links. Powerful when combined '
                      'with collective.recipe.omelette.')
    parser.add_option('-n', '--dry-run', action='store_true', dest='dryrun',
                      help='Run the script without creating files')
    parser.add_option('-e', '--separate', action='store_true',
                      dest='separatemodules',
                      help='Put documentation for each module on its own page')
    parser.add_option('-P', '--private', action='store_true',
                      dest='includeprivate',
                      help='Include "_private" modules')
    parser.add_option('-T', '--no-toc', action='store_true', dest='notoc',
                      help='Don\'t create a table of contents file')
    parser.add_option('-E', '--no-headings', action='store_true',
                      dest='noheadings',
                      help='Don\'t create headings for the module/package '
                           'packages (e.g. when the docstrings already contain '
                           'them). No effect in combination with -t')
    parser.add_option('-M', '--module-first', action='store_true',
                      dest='modulefirst',
                      help='Put module documentation before submodule '
                      'documentation (no effect in combination with -t)')
    parser.add_option('--implicit-namespaces', action='store_true',
                      dest='implicit_namespaces',
                      help='Interpret module paths according to PEP-0420 '
                           'implicit namespaces specification')
    parser.add_option('-s', '--suffix', action='store', dest='suffix',
                      help='file suffix (default: rst)', default='rst')
    parser.add_option('-F', '--full', action='store_true', dest='full',
                      help='Generate a full project with sphinx-quickstart')
    parser.add_option('-a', '--append-syspath', action='store_true',
                      dest='append_syspath',
                      help='Append module_path to sys.path, used when --full is given')
    parser.add_option("-t", "--templates", action="store", type="string",
                      dest="templates", default=None,
                      help="Custom template directory (default: %default). "
                      "Must contain template files package.rst and/or "
                      "module.rst")
    parser.add_option('-H', '--doc-project', action='store', dest='header',
                      help='Project name (default: root module name)')
    parser.add_option('-A', '--doc-author', action='store', dest='author',
                      type='str',
                      help='Project author(s), used when --full is given')
    parser.add_option('-V', '--doc-version', action='store', dest='version',
                      help='Project version, used when --full is given')
    parser.add_option('-R', '--doc-release', action='store', dest='release',
                      help='Project release, used when --full is given, '
                      'defaults to --doc-version')
    parser.add_option('--version', action='store_true', dest='show_version',
                      help='Show version information and exit')
    group = parser.add_option_group('Extension options')
    for ext in EXTENSIONS:
        group.add_option('--ext-' + ext, action='store_true',
                         dest='ext_' + ext, default=False,
                         help='enable %s extension' % ext)

    (opts, args) = parser.parse_args(argv[1:])

    if opts.show_version:
        #print('Sphinx (sphinx-apidoc) %s' % __display_version__)
        print('better-apidoc %s' % __display_version__)
        return 0

    if not args:
        parser.error('A package path is required.')

    rootpath, excludes = args[0], args[1:]
    if not opts.destdir:
        parser.error('An output directory is required.')
    if opts.header is None:
        opts.header = path.abspath(rootpath).split(path.sep)[-1]
    if opts.suffix.startswith('.'):
        opts.suffix = opts.suffix[1:]
    if not path.isdir(rootpath):
        print('%s is not a directory.' % rootpath, file=sys.stderr)
        sys.exit(1)
    if not path.isdir(opts.destdir):
        if not opts.dryrun:
            os.makedirs(opts.destdir)
    rootpath = path.abspath(rootpath)
    excludes = normalize_excludes(rootpath, excludes)
    try:
        modules = recurse_tree(rootpath, excludes, opts)
    except TemplateNotFound as e:
        print('Cannot find template in %s: %s' %
              (opts.templates, e), file=sys.stderr)
        sys.exit(1)

    if opts.full:
        raise NotImplementedError("--full not supported")
        # This would only make sense if this script was integrated in Sphinx
        from sphinx import quickstart as qs
        modules.sort()
        prev_module = ''  # type: unicode
        text = ''
        for module in modules:
            if module.startswith(prev_module + '.'):
                continue
            prev_module = module
            text += '   %s\n' % module
        d = dict(
            path = opts.destdir,
            sep = False,
            dot = '_',
            project = opts.header,
            author = opts.author or 'Author',
            version = opts.version or '',
            release = opts.release or opts.version or '',
            suffix = '.' + opts.suffix,
            master = 'index',
            epub = True,
            ext_autodoc = True,
            ext_viewcode = True,
            ext_todo = True,
            makefile = True,
            batchfile = True,
            mastertocmaxdepth = opts.maxdepth,
            mastertoctree = text,
            language = 'en',
            module_path = rootpath,
            append_syspath = opts.append_syspath,
        )
        enabled_exts = {'ext_' + ext: getattr(opts, 'ext_' + ext)
                        for ext in EXTENSIONS if getattr(opts, 'ext_' + ext)}
        d.update(enabled_exts)

        if isinstance(opts.header, binary_type):
            d['project'] = d['project'].decode('utf-8')
        if isinstance(opts.author, binary_type):
            d['author'] = d['author'].decode('utf-8')
        if isinstance(opts.version, binary_type):
            d['version'] = d['version'].decode('utf-8')
        if isinstance(opts.release, binary_type):
            d['release'] = d['release'].decode('utf-8')

        if not opts.dryrun:
            qs.generate(d, silent=True, overwrite=opts.force)
    elif not opts.notoc:
        create_modules_toc_file(modules, opts)
    return 0


# So program can be started with "python -m sphinx.apidoc ..."
#if __name__ == "__main__":
    #main()
