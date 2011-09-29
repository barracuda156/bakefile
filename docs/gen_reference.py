#!/usr/bin/env python

#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2008-2011 Vaclav Slavik
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
#  IN THE SOFTWARE.
#

"""
This tool generates reference documentation for Bakefile plugins and puts
it in ref/ directory.
"""

import sys
import os
import os.path
import types
import shutil
import sphinx.util.docstrings
from functools import partial

docs_path = os.path.dirname(sys.argv[0])
bkl_path = os.path.normpath(os.path.join(docs_path, "..", "src"))
sys.path = [bkl_path] + sys.path

import bkl
import bkl.api
from bkl.props import registry

OUT_DIR = os.path.join(docs_path, "ref")
shutil.rmtree(OUT_DIR, ignore_errors=True)
os.makedirs(OUT_DIR)


def underline(s, how):
    u = "".join(how for i in xrange(0, len(s)))
    return "%s\n%s" % (s,u)


def prop_scope(symbolic):
    if symbolic == "properties":
        return ""
    if symbolic.startswith("properties_"):
        symbolic = symbolic[len("properties_"):]

    human = {
        bkl.api.Property.SCOPE_PROJECT : "Global to project",
        bkl.api.Property.SCOPE_MODULE : "Modules",
        bkl.api.Property.SCOPE_TARGET : "All targets",
        }
    if symbolic in human:
        return human[symbolic]

    assert False, "unrecognized scope"


def write_property(prop):
    desc = ""
    if prop.__doc__:
        desc += prop.__doc__
        desc += "\n"

    if prop.toolsets:
        toolsets = (":ref:`ref_toolset_%s`" % x for x in prop.toolsets)
        desc += "\n*Only for toolsets:* %s\n" % (", ".join(toolsets))

    if prop.readonly:
        desc += "\n*Read-only property*\n"
    else:
        if prop.default is None:
            desc += "\n*Required property*\n"
        else:
            default = prop.default
            if default == []:
                default = "empty"
            elif ((isinstance(default, types.FunctionType) or
                 isinstance(default, types.MethodType)) and
                "__doc__" in dir(default)):
                default = default.__doc__
            desc += "\n*Default:* %s\n" % default

    txt = "**%s** (type: %s)\n\n" % (prop.name, prop.type.name)
    txt += "    " + "\n    ".join(desc.split("\n"))
    txt += "\n"
    return txt


def write_properties(props_func):
    props = list(props_func())
    if not props:
        return ""

    txt = "\n\nProperties\n----------\n\n"

    for p in props:
        txt += write_property(p)

    return txt



DOC_TEMPLATE = """
.. This file was generated by gen_reference.py, don't edit manually!

.. _%(reflabel)s:

%(title)s

%(docstring)s
"""

def write_docs(filename, title, docstring):
    """
    Writes out documentation to a file.
    """
    reflabel = "ref_%s" % filename
    title = underline(title, "=")
    f = open("%s/%s.rst" % (OUT_DIR, filename), "wt")
    f.write(DOC_TEMPLATE % locals())


def write_extension_docs(kind, extension, props_func=None):
    """
    Writes out documentation for extension of given kind.
    """
    name = extension.name
    print "documenting %s %s..." % (kind, name)
    docstring = sphinx.util.docstrings.prepare_docstring(extension.__doc__)

    title = name
    if len(docstring) > 0:
        summary = docstring[0]
        if summary[-1] == ".":
            title = "%s *(%s)*" % (summary[:-1], name)

    docstring_text = "\n".join(docstring)

    if props_func is not None:
        docstring_text += write_properties(props_func)
    else:
        ptext = "\n\n%s\n\n" % underline("Properties", "-")
        for pkind in extension.all_properties_kinds():
            pall = list(extension.all_properties(pkind))
            if pall:
                ptext += "\n\n%s\n\n" % underline(prop_scope(pkind), "^")
                for p in pall:
                    ptext += write_property(p)
        docstring_text += ptext

    write_docs("%s_%s" % (kind, name), title, docstring_text)




# write docs for all targets:
for t in bkl.api.TargetType.all():
    write_extension_docs("target", t, partial(registry.enum_target_props, t))

# write docs for all toolsets:
for t in bkl.api.Toolset.all():
    write_extension_docs("toolset", t)

# write docs for projects/modules:
write_docs("project", "Global project properties",
           write_properties(registry.enum_project_props))
write_docs("module", "Module properties",
           write_properties(registry.enum_module_props))
