#!/usr/bin/python

import sys
import re

import libxltypes

def format_comment(level, comment):
    indent = reduce(lambda x,y: x + " ", range(level), "")
    s  = "%s/*\n" % indent
    s += "%s * " % indent
    comment = comment.replace("\n", "\n%s * " % indent)
    x = re.compile(r'^%s \* $' % indent, re.MULTILINE)
    comment = x.sub("%s *" % indent, comment)
    s += comment
    s += "\n"
    s += "%s */" % indent
    s += "\n"
    return s

def libxl_C_type_of(ty):
    return ty.typename

def libxl_C_instance_of(ty, instancename):
    if isinstance(ty, libxltypes.BitField):
        return libxl_C_type_of(ty) + " " + instancename + ":%d" % ty.width
    elif isinstance(ty, libxltypes.Aggregate) and ty.typename is None:
        if instancename is None:
            return libxl_C_type_define(ty)
        else:
            return libxl_C_type_define(ty) + " " + instancename
    else:
        return libxl_C_type_of(ty) + " " + instancename

def libxl_C_type_define(ty, indent = ""):
    s = ""
    if isinstance(ty, libxltypes.Aggregate):
        if ty.comment is not None:
            s += format_comment(0, ty.comment)

        if ty.typename is None:
            s += "%s {\n" % ty.kind
        else:
            s += "typedef %s {\n" % ty.kind

        for f in ty.fields:
            if f.comment is not None:
                s += format_comment(4, f.comment)
            x = libxl_C_instance_of(f.type, f.name)
            if f.const:
                x = "const " + x
            x = x.replace("\n", "\n    ")
            s += "    " + x + ";\n"
        if ty.typename is None:
            s += "}"
        else:
            s += "} %s" % ty.typename
    else:
        raise NotImplementedError("%s" % type(ty))
    return s.replace("\n", "\n%s" % indent)

def libxl_C_type_destroy(ty, v, reference, indent = "    ", parent = None):
    if reference:
        deref = v + "->"
    else:
        deref = v + "."

    s = ""
    if isinstance(ty, libxltypes.KeyedUnion):
        if parent is None:
            raise Exception("KeyedUnion type must have a parent")
        for f in ty.fields:
            keyvar_expr = f.keyvar_expr % (parent + ty.keyvar_name)
            s += "if (" + keyvar_expr + ") {\n"
            s += libxl_C_type_destroy(f.type, deref + f.name, False, indent + "    ", deref)
            s += "}\n"
    elif isinstance(ty, libxltypes.Reference):
        s += libxl_C_type_destroy(ty.ref_type, v, True, indent, v)
    elif isinstance(ty, libxltypes.Struct) and (parent is None or ty.destructor_fn is None):
        for f in [f for f in ty.fields if not f.const]:

            if f.name is None: # Anonynous struct
                s += libxl_C_type_destroy(f.type, deref, False, "", deref)
            else:
                s += libxl_C_type_destroy(f.type, deref + f.name, False, "", deref)
    else:
        if ty.passby == libxltypes.PASS_BY_REFERENCE and not reference:
            makeref = "&"
        else:
            makeref = ""

        if ty.destructor_fn is not None:
            s += "%s(%s);\n" % (ty.destructor_fn, makeref + v)
            
    if s != "":
        s = indent + s
    return s.replace("\n", "\n%s" % indent).rstrip(indent)

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print >>sys.stderr, "Usage: gentypes.py <idl> <header> <implementation>"
        sys.exit(1)

    idl = sys.argv[1]
    (_,types) = libxltypes.parse(idl)
                    
    header = sys.argv[2]
    print "outputting libxl type definitions to %s" % header

    f = open(header, "w")
    
    f.write("""#ifndef __LIBXL_TYPES_H
#define __LIBXL_TYPES_H

/*
 * DO NOT EDIT.
 *
 * This file is autogenerated by
 * "%s"
 */
 
""" % " ".join(sys.argv))
        
    for ty in types:
        f.write(libxl_C_type_define(ty) + ";\n")
        if ty.destructor_fn is not None:
            f.write("void %s(%s *p);\n" % (ty.destructor_fn, ty.typename))
        f.write("\n")

    f.write("""#endif /* __LIBXL_TYPES_H */\n""")
    f.close()
    
    impl = sys.argv[3]
    print "outputting libxl type implementations to %s" % impl

    f = open(impl, "w")
    f.write("""
/* DO NOT EDIT.
 *
 * This file is autogenerated by
 * "%s"
 */

#include "libxl_osdeps.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "libxl.h"

#define LIBXL_DTOR_POISON 0xa5

""" % " ".join(sys.argv))

    for ty in [t for t in types if t.destructor_fn is not None and t.autogenerate_destructor]:
        f.write("void %s(%s *p)\n" % (ty.destructor_fn, ty.typename))
        f.write("{\n")
        f.write(libxl_C_type_destroy(ty, "p", True))
        f.write("\tmemset(p, LIBXL_DTOR_POISON, sizeof(*p));\n")
        f.write("}\n")
        f.write("\n")
    f.close()
