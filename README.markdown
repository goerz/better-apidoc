# better-apidoc #

A version of [sphinx-apidoc][] with support for templating

Author: Michael Goerz <<goerz@stanford.edu>>

Website: [Github][]

[Github]: https://github.com/goerz/better-apidoc#better-apidoc
[sphinx-apidoc]: http://www.sphinx-doc.org/en/stable/man/sphinx-apidoc.html


## Installation ##

    pip install better-apidoc

This will install `better-apidoc` in the current environment's `bin` folder.

[virtualenv]: http://docs.python-guide.org/en/latest/dev/virtualenvs/
[pipsi]: https://github.com/mitsuhiko/pipsi#pipsi
[conda env]: http://conda.pydata.org/docs/using/envs.html

## Templating ##

The `better-apidoc` script is a patched version of Sphinx' [apidoc.py]. If
well-received, I may try to have this patch merged back into Sphinx as an update
to `sphinx-apidoc`.

It adds the `-t/--templates` option to the script. If this option is not given,
it is identical to `sphinx-apidoc`. With the option, [Jinja]-based templates
are used for the generated ReST files. The template directory given via `-t`
must contain the template files `module.rst` and `package.rst`.

The following variables are available in the templates:

* *name*: the name of the module/package
* *fullname*: the name of the module/package, including package path
  (dot-separated)
* *members*: list of names of all the members defined directly in the
  module/package
* *functions*: list all the functions in *members*
* *classes*: list of all the classes in *members*
* *exceptions*: list of all the exceptions in *members*
* *data*: list of all the data items in *members*
* *member_imports*: list of all members in the module/package, including those
  imported
* *members_imports_refs*: list of ReST-formatted references of all the items in
  *member_imports*. For imported items, these link to the original locations
  where these items are defined
* *all_refs*: list of ReST-formatted references for all items appearing in the
  `__all__`-list of the module/package
* *subpackages*: For packages, list of subpackage names. Empty list for modules
* *submodules*: For packages, list of submodule names. Empty list of modules

The `package.rst` template will be used when rendering any package. The
`module.rst` template will be used when rendering modules if the
`-s/--separate` option is given, or if the `<module_path>` only contains
modules. Note that if `<module_path>` contains a package and the `-s/--separate`
is not given, the `module.rst` template will not be used.

In some circumstances, special care must be taken when generating API
documentation for modules that contain module data (e.g., constants). Since the
template variables are determined from an import for the module (as opposed to
parsing the module source code), there is no way to distinguish locally defined
data from imported data. Module data will be considered imported (i.e., it will
not show up in *data*, only in *member_imports*) unless one of the following two
conditions is met:

* the name of the data member appears in the `__all__` list of the module
* the name of the data member appears in a list `__local_data__` of the
  module. This list is a custom convention of the `better-apidoc` script.

In cases where a data member appears in `__all__` but is not locally defined,
the module may define a dictionary [`__imported_data__`] that maps the name of the
data member of a ReST-formatted reference string for `better-apidoc` to
correctly classify the member.

The addition of templates to `apidoc` addresses [Sphinx issue #3545]. That is, it
is now possible to have a list of members with short summaries at the top of the
API documentation that links to the more detailed information below.
It is also directly addresses the demand for this feature expressed on
[Stackoverflow].

See
[package.rst](https://github.com/mabuchilab/QNET/blob/develop/docs/_templates/package.rst)
and
[module.rst](https://github.com/mabuchilab/QNET/blob/develop/docs/_templates/module.rst)
for an example template. These render to e.g.
<http://qnet.readthedocs.io/en/latest/API/qnet.algebra.operator_algebra.html>


[apidoc.py]: https://github.com/sphinx-doc/sphinx/blob/master/sphinx/apidoc.py
[Jinja]: http://jinja.pocoo.org
[`__imported_data__`]: https://github.com/mabuchilab/QNET/blob/4e637b18c53cbee598ed58c3b7f7820dd54216db/qnet/algebra/__init__.py#L56
[Sphinx issue #3545]: https://github.com/sphinx-doc/sphinx/issues/3545
[Stackoverflow]: http://stackoverflow.com/questions/29385564/customize-templates-for-sphinx-apidoc


## Usage ##

See `better-apidoc -h`

You can also use this as a module `better_apidoc`, e.g. from the Sphinx
`conf.py` file to automate the generation of API files. For an example, see the
[`conf.py` file of the QNET project][QNETconf]

[QNETconf]: https://github.com/mabuchilab/QNET/blob/8cb1775396b1ceab69a498001cef33d063344f9d/docs/conf.py#L35


## License ##

This software is available under the terms of the BSD license. See [LICENSE]
for details.

[LICENSE]: LICENSE
