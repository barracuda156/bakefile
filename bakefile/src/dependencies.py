#
#  This file is part of Bakefile (http://bakefile.sourceforge.net)
#
#  Copyright (C) 2003,2004 Vaclav Slavik
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License version 2 as
#  published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#  $Id$
#
#  Keeping track of dependencies
#

import cPickle, os.path, time

DEPS_FORMAT_VERSION = 4

class DepsRecord:
    def __init__(self):
        self.deps = []
        self.outputs = [] # (filename,method) tuples

deps_db = {}
modtimes_db = {}
cmdlines_db = {}

def addDependency(bakefile, format, dependency_file):
    """Adds file 'dependency_file' as dependency of bakefile being
       processed."""
    if bakefile == dependency_file: return
    key = (bakefile,format)
    if key not in deps_db:
        deps_db[key] = DepsRecord()
    deps_db[key].deps.append(dependency_file)

def addOutput(bakefile, format, output_file, output_method):
    """Adds file 'output_file' as output created by the bakefile being
       processed."""
    key = (bakefile,format)
    if key not in deps_db:
        deps_db[key] = DepsRecord()
    deps_db[key].outputs.append((output_file, output_method))
    modtimes_db[output_file] = int(time.time())

def addCmdLine(bakefile, format, cmdline):
    """Records that command line arguments `cmdline' were used when
       generating this bakefile."""
    key = (bakefile,format)
    cmdlines_db[key] = cmdline
    
def save(filename):
    """Saves dependencies database to a file."""
    f = open(filename,'wb')
    cPickle.dump(DEPS_FORMAT_VERSION, f, 1)
    cPickle.dump(deps_db, f, 1)
    cPickle.dump(modtimes_db, f, 1)
    cPickle.dump(cmdlines_db, f, 1)
    f.close()

def load(filename):
    """Loads dependencies database from a file."""
    f = open(filename,'rb')
    global deps_db, modtimes_db, cmdlines_db
    version = cPickle.load(f)
    if version != DEPS_FORMAT_VERSION:
        raise IOError()

    def __loadDb(f, orig_db):
        db = cPickle.load(f)
        if len(orig_db) == 0:
            return db
        else:
            for k in db:
                orig_db[k] = db[k]
            return orig_db
        
    deps_db = __loadDb(f, deps_db)
    modtimes_db = __loadDb(f, modtimes_db)
    cmdlines_db = __loadDb(f, cmdlines_db)


def needsUpdate(bakefile, format, cmdline):
    """Determines whether the generated makefile in given format from the
       bakefile needs updating, assuming bakefile will be called with
       arguments in `cmdline'."""
    key = (bakefile, format)
    if (key not in deps_db) or (key not in cmdlines_db):
        # no knowledge of deps or output or command line, must regen:
        return 1

    # bakefile invocation changed, may affect the output:
    if cmdline != cmdlines_db[key]:
        return 1

    bakefile_time = os.stat(bakefile).st_mtime

    info = deps_db[key]
    oldest_output = None
    for f, method in info.outputs:
        if not os.path.isfile(f):
            # one of generate files is missing, we must regen:
            return 1
        f_time = os.stat(f).st_mtime
        if f in modtimes_db:
            if modtimes_db[f] > f_time: f_time = modtimes_db[f]
        if oldest_output == None or f_time < oldest_output:
            oldest_output = f_time

    if oldest_output == None:
        return 1

    if oldest_output < bakefile_time:
        return 1

    for f in info.deps:
        if not os.path.isfile(f):
            # one of dependencies is missing, we must regen:
            return 1
        if oldest_output < os.stat(f).st_mtime:
            # one of used bakefiles is newer than generated files:
            return 1

    # this bakefile's output is up-to-date
    return 0