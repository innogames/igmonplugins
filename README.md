InnoGames Monitoring Plugins
============================

This repository is only for Nagios compatible scripts developed by
InnoGames.  We have packages for more complicated checks.  This
repository is only for standalone simple scripts which don't worth
having separate packages.  Please don't bloat it.

Language
--------

Python is our preferred language at InnoGames System Administration.
Please write the new plugins in Python unless you have a very good
reason to use another language.  Particularly any kind of shell
scripting is not acceptable for anything new.

The scripts should run on Python 3.5 and later.  Python 2.7 compatibility
is optional but recommended for the ones that are generally useful.

Style Guide
-----------

The scripts are named with lower-case underscore notation.  The scripts
must have file extensions.  The checks should be prefixed with "check\_".
Not portable ones should include the operating system they are working
on in their names.

License
-------

The scripts are released under the MIT License.  The license is
included on the file headers.  The MIT License is registered with
and approved by the Open Source Initiative [1].

[1] https://opensource.org/licenses/MIT
