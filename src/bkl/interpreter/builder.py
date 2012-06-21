#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2008-2012 Vaclav Slavik
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

from ..api import TargetType
from ..expr import *
from ..model import Module, Target, Variable, SourceFile
from ..parser.ast import *
from ..error import ParserError, error_context, warning
from ..vartypes import ListType, AnyType

import os.path

import logging
logger = logging.getLogger("bkl.interpreter.builder")


class Builder(object, CondTrackingMixin):
    """
    interpreter.Builder processes parsed AST and builds a project model
    from it.

    It doesn't do anything smart like optimizing things, it does only the
    minimal processing needed to produce a valid, albeit suboptimal, model.

    This includes checking variables scopes etc., but does *not* involve
    checks for type correctness. Passes further in the
    :class:`bkl.interpreter.Interpreter` pipeline handle that.

    .. attribute:: context

       Current context. This is the inner-most :class:`bkl.model.ModelPart`
       at the time of parsing. Initially, it is set to a new
       :class:`bkl.model.Module` instance by :meth:`create_model`. When
       descending into a target, it is temporarily set to said target and
       then restored and so on.
    """
    def __init__(self, on_submodule=None):
        """
        Constructor.

        :param on_module: Callback to call (with filename as argument) on
                ``submodule`` statement.
        """
        CondTrackingMixin.__init__(self)
        self.context = None
        self.on_submodule_callback = on_submodule


    def create_model(self, ast, parent):
        """Returns constructed model, as :class:`bkl.model.Module` instance."""
        mod = Module(parent, source_pos=ast.pos)
        mod.source_pos.line = mod.source_pos.column = None
        self.context = mod

        self.handle_children(ast.children, self.context)
        assert self.context is mod

        return mod


    def create_expression(self, ast, parent):
        """Creates :class:`bkl.epxr.Expr` expression in given parent's context."""
        self.context = parent
        return self._build_expression(ast)


    def handle_children(self, children, context):
        """
        Runs model creation of all children nodes.

        :param children: List of AST nodes to treat as children.
        :param context:  Context (aka "local scope"). Interpreter's
               :attr:`context` is set to it for the duration of the call.
        """
        try:
            old_ctxt = self.context
            self.context = context
            for n in children:
                self._handle_node(n)
        finally:
            self.context = old_ctxt


    def _handle_node(self, node):
        func = self._ast_dispatch[type(node)]
        # Assign position to the error if it wasn't done already; it's
        # often more convenient to do it here than to keep track of the
        # position across a hierarchy of nested calls.
        with error_context(node):
            func(self, node)


    def on_assignment(self, node):
        append = node.append
        value = self._build_expression(node.value)
        has_cond = self.active_if_cond is not None

        varname = node.var
        if varname[0] == "_":
            warning("variable names beginning with underscore are reserved for internal use (\"%s\")",
                    varname, pos=node.pos)

        var = self.context.get_variable(varname)
        if var is None:
            # the variable may still exist in a higher scope, in which case we
            # need to inherit the value from that, not from a property
            previous_value = self.context.resolve_variable(varname)
        else:
            previous_value = var

        if var is None:
            # If there's an appropriate property with the same name, then
            # this assignment expression needs to be interpreted as assignment
            # to said property. In other words, the new variable's type
            # must much that of the property.
            prop = self.context.get_prop(varname)
            if prop:
                if append or has_cond:
                    propval = prop.default_expr(self.context)
                else:
                    propval = NullExpr() # we'll set it below
                var = Variable.from_property(prop, propval)
                self.context.add_variable(var)
                # and if we didn't get previous value from anywhere else yet,
                # we'll need to use the property:
                if previous_value is None:
                    previous_value = var

        # if the value is set conditionally, modify 'value' so that it reflects
        # the condition:
        if has_cond:
            if append:
                # If conditionally appending more items to an existing list,
                # it's better to associate the condition with individual items.
                if isinstance(value, ListExpr):
                    ifs = [IfExpr(self.active_if_cond,
                                  yes=i,
                                  no=NullExpr(),
                                  pos=i.pos)
                           for i in value.items]
                    value = ListExpr(ifs, pos=value.pos)
                else:
                    value = IfExpr(self.active_if_cond,
                                   yes=value,
                                   no=NullExpr(),
                                   pos=node.pos)
            else:
                # But when just setting the value, keep it all together as
                # a single value inside single IfExpr.
                value = IfExpr(self.active_if_cond,
                               yes=value,
                               no=previous_value.value if previous_value else NullExpr(),
                               pos=node.pos)

        # create the variable if necessary:
        if var is None:
            if append and previous_value is None:
                raise ParserError('unknown variable "%s"' % varname)
            if previous_value:
                var = Variable(varname, previous_value.value, previous_value.type)
            else:
                var = Variable(varname, value)
            self.context.add_variable(var)

        # finally, modify variable value:
        if append:
            assert previous_value is not None
            if not isinstance(var.type, ListType):
                if isinstance(var.type, AnyType):
                    # if the type is undetermined, it can as well be a list
                    var.type = ListType(var.type)
                else:
                    raise ParserError('cannot append to non-list variable "%s" (type: %s)' %
                                      (varname, var.type))
            if isinstance(value, ListExpr):
                new_values = value.items
            else:
                new_values = [value]
            if isinstance(previous_value.value, ListExpr):
                value = ListExpr(previous_value.value.items + new_values)
            else:
                value = ListExpr([previous_value.value] + new_values)
            value.pos = node.pos
            var.set_value(value)
        else:
            var.set_value(value)


    def on_sources_or_headers(self, node):
        if node.kind == "sources":
            filelist = self.context.sources
        elif node.kind == "headers":
            filelist = self.context.headers
        else:
            assert False, 'invalid files list kind "%s"' % node.kind

        files = self._build_expression(node.files)
        for cond, f in enum_possible_values(files, global_cond=self.active_if_cond):
            obj = SourceFile(self.context, f, source_pos=f.pos)
            if cond is not None:
                obj.set_property_value("_condition", cond)
            filelist.append(obj)


    def on_target(self, node):
        name = node.name.text
        if self.context.project.has_target(name):
            raise ParserError("target with ID \"%s\" already exists (see %s)" %
                              (name, self.context.project.get_target(name).source_pos))

        type_name = node.type.text

        try:
            target_type = TargetType.get(type_name)
            target = Target(self.context, name, target_type, source_pos=node.pos)
            if self.active_if_cond is not None:
                target.set_property_value("_condition", self.active_if_cond)
        except KeyError:
            raise ParserError("unknown target type \"%s\"" % type_name)

        # handle target-specific variables assignments etc:
        condstack = self.reset_cond_stack()
        self.handle_children(node.content, target)
        self.restore_cond_stack(condstack)


    def on_if(self, node):
        self.push_cond(self._build_expression(node.cond))
        self.handle_children(node.content, self.context)
        self.pop_cond()


    def on_configuration(self, node):
        project = self.context.project
        if node.name in ["Debug", "Release"]:
            if node.base:
                raise ParserError("Debug and Release configurations can't be derived from another")
            cfg = project.configurations[node.name]
        else:
            if not node.base:
                raise ParserError("configurations other than Debug and Release must derive from another")
            if node.name in project.configurations:
                raise ParserError("configuration \"%s\" already defined (at %s)" %
                                  (node.name, project.configurations[node.name].source_pos))

            try:
                base = project.configurations[node.base]
                cfg = base.clone(node.name, source_pos=node.pos)
                project.add_configuration(cfg)
            except KeyError:
                raise ParserError("unknown base configuration \"%s\"" % node.base)
        if node.base:
            cfg._definition = project.configurations[node.base]._definition + node.content
        else:
            cfg._definition = node.content

        config_cond = BoolExpr(BoolExpr.EQUAL,
                               ReferenceExpr("config", self.context),
                               LiteralExpr(node.name),
                               pos=node.pos)
        self.push_cond(config_cond)
        self.handle_children(cfg._definition, self.context)
        self.pop_cond()


    def on_submodule(self, node):
        if self.active_if_cond is not None:
            raise ParserError("conditionally included submodules not supported yet"
                              ' (condition "%s" set at %s)' % (
                                  self.active_if_cond, self.active_if_cond.pos))
        fn = os.path.relpath(os.path.join(os.path.dirname(node.pos.filename), node.file))
        self.on_submodule_callback(fn, node.pos)


    def on_srcdir(self, node):
        assert isinstance(self.context, Module)
        assert self.active_if_cond is None

        srcdir = os.path.normpath(os.path.join(os.path.dirname(self.context.source_file),
                                               node.srcdir))
        logger.debug("setting @srcdir for %s to %s", self.context, srcdir)
        self.context.srcdir = srcdir


    _ast_dispatch = {
        AssignmentNode     : on_assignment,
        AppendNode         : on_assignment,
        FilesListNode      : on_sources_or_headers,
        TargetNode         : on_target,
        IfNode             : on_if,
        ConfigurationNode  : on_configuration,
        SubmoduleNode      : on_submodule,
        SrcdirNode         : on_srcdir,
        NilNode            : lambda self,x: x, # do nothing
    }


    def _build_expression(self, ast):
        t = type(ast)
        if t is LiteralNode:
            # FIXME: type handling
            e = LiteralExpr(ast.text)
        elif t is BoolvalNode:
            e = BoolValueExpr(ast.value)
        elif t is VarReferenceNode:
            e= ReferenceExpr(ast.var, self.context)
        elif t is ListNode:
            items = [self._build_expression(e) for e in ast.values]
            e = ListExpr(items)
        elif t is ConcatNode:
            items = [self._build_expression(e) for e in ast.values]
            e = ConcatExpr(items)
        elif isinstance(ast, BoolNode):
            e = self._build_bool_expression(ast)
        else:
            assert False, "unrecognized AST node (%s)" % ast
        e.pos = ast.pos
        return e


    def _build_bool_expression(self, ast):
        t = type(ast)
        if t is NotNode:
            return BoolExpr(BoolExpr.NOT, self._build_expression(ast.left))
        else:
            if t is AndNode:
                op = BoolExpr.AND
            elif t is OrNode:
                op = BoolExpr.OR
            elif t is EqualNode:
                op = BoolExpr.EQUAL
            elif t is NotEqualNode:
                op = BoolExpr.NOT_EQUAL
            left = self._build_expression(ast.left)
            right = self._build_expression(ast.right)
            return BoolExpr(op, left, right)
