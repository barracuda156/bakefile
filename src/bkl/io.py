#
#  This file is part of Bakefile (http://www.bakefile.org)
#
#  Copyright (C) 2009-2012 Vaclav Slavik
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
Helper classes for Bakefile I/O. Manages atomic writing of output, detecting
changes, line endings conversions etc.
"""

import os
import os.path

import logging
logger = logging.getLogger("bkl.io")


# Set to true to prevent any output from being written
dry_run = False


EOL_WINDOWS = "win"
EOL_UNIX    = "unix"


class OutputFile(object):
    """
    File to be written by Bakefile.

    Example usage:

    ::

      f = io.OutputFile("Makefile")
      f.write(body)
      f.commit()

    Notice the need to explicitly call commit().
    """
    def __init__(self, filename, eol, charset="utf-8"):
        """
        Creates output file.

        :param filename: Name of the output file. Should be either relative
                         to CWD or absolute; the latter is recommended.
        :param eol:      Line endings to use. One of EOL_WINDOWS and EOL_UNIX.
        :param charset:  Charset to use if Unicode string is passed to write().
        """
        self.filename = filename
        self.eol = eol
        self.charset = charset
        self.text = ""

    def write(self, text):
        """
        Writes text to the output, performing line endings conversion as
        needed. Note that the changes don't take effect until you call
        commit().
        """
        if isinstance(text, unicode):
            text = text.encode(self.charset)
        self.text += text

    def commit(self):
        if self.eol == EOL_WINDOWS:
            self.text = self.text.replace("\n", "\r\n")

        try:
            with open(self.filename, "rb") as f:
                old = f.read()
        except IOError:
            old = None

        note = " (dry run)" if dry_run else ""

        if old == self.text:
            logger.info("no changes in file %s", self.filename)
        else:
            if old is None:
                logger.info("creating file %s%s", self.filename, note)
            else:
                logger.info("updating file %s%s", self.filename, note)

            if dry_run:
                return # nothing to do, just pretending to write output

            dirname = os.path.dirname(self.filename)
            if dirname and not os.path.isdir(dirname):
                os.makedirs(dirname)
            with open(self.filename, "wb") as f:
                f.write(self.text)