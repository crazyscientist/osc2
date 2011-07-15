"""Provides some utility functions to get data from a
working copy without constructing a Project or Package
instance.

"""

import os
import errno
import fcntl
from tempfile import NamedTemporaryFile

__all__ = ['wc_is_project', 'wc_is_package', 'wc_read_project',
           'wc_read_package', 'wc_read_apiurl']

# maybe we should define this somewhere else
_STORE = '.osc'
_PKG_DATA = 'data'
_LOCK = 'wc.lock'

class WCInconsistentError(Exception):
    """Represents an invalid working copy state"""

    def __init__(self, path, meta=(), xml_data=None, data=()):
        super(WCInconsistentError, self).__init__()
        self.path = path
        self.meta = meta
        self.xml_data = xml_data
        self.data = data


class WCLock(object):
    """Represents a lock on a working copy.

    "Coordinates" working copy locking.

    """

    def __init__(self, path):
        """Constructs a new WCLock object.

        path is the path to wc working copy.
        No lock is acquired (it must be explicitly locked
        via the lock() method).

        """
        super(WCLock, self).__init__()
        self._path = path
        self._fobj = None

    def has_lock(self):
        """Check if this object has lock on the working copy.

        Return True if it holds a lock otherwise False.

        """
        return self._fobj is not None

    def lock(self):
        """Acquire the lock on the working copy.

        This call might block if the working copy is already
        locked.
        A RuntimeError is raised if this object already
        has a lock on the working copy.

        """
        if self.has_lock():
            # a double lock is no problem at all but if it occurs
            # it smells like a programming/logic error (IMHO)
            raise RuntimeError('Double lock occured')
        global _LOCK
        lock = _storefile(self._path, _LOCK)
        f = open(lock, 'w')
        fcntl.lockf(f, fcntl.LOCK_EX)
        self._fobj = f

    def unlock(self):
        """Release the lock on the working copy.

        If the working copy wasn't locked before a
        RuntimeError is raised.

        """
        if not self.has_lock():
            raise RuntimeError('Attempting to release an unaquired lock.')
        fcntl.lockf(self._fobj, fcntl.LOCK_UN)
        self._fobj.close()
        self._fobj = None
        global _LOCK
        lock = _storefile(self._path, _LOCK)
        os.unlink(lock)

    def __enter__(self):
        self.lock()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unlock()
        # don't suppress any exception
        return False


def _storedir(path):
    """Return the storedir path"""
    global _STORE
    return os.path.join(path, _STORE)

def _storefile(path, filename):
    """Return the path to the storefile"""
    return os.path.join(_storedir(path), filename)

def _has_storedir(path):
    """Test if path has a storedir (internal function)"""
    storedir = _storedir(path)
    return os.path.isdir(path) and os.path.isdir(storedir)

def missing_storepaths(path, *paths, **kwargs):
    """Test if the path/storedir contains all *paths

    All missing paths will be returned. If the returned
    list is empty all *path are available.

    Keyword arguments:
    dirs -- specifies if each path should be treated as a
            file or as a directory (default: False)
    data -- the paths are expected to exist in storedir/_PKG_DATA


    """
    dirs = kwargs.get('dirs', False)
    data = kwargs.get('data', False)
    if not _has_storedir(path):
        return list(paths)
    storedir = _storedir(path)
    if data:
        global _PKG_DATA
        storedir = _storefile(path, _PKG_DATA)
    missing = []
    for p in paths:
        storepath = os.path.join(storedir, p)
        if dirs:
            if not os.path.isdir(storepath):
                missing.append(p)
        else:
            if not os.path.isfile(storepath):
                missing.append(p)
    return missing

def _read_storefile(path, filename):
    """Read the content of the path/storedir/filename.

    If path/storedir/filename does not exist or is no file
    a ValueError is raised.
    Leading and trailing whitespaces, tabs etc. are stripped.

    """
    if missing_storepaths(path, filename):
        # file does not exist or is no file
        msg = "'%s' is no valid storefile" % filename
        raise ValueError(msg)
    storefile = _storefile(path, filename)
    with open(storefile, 'r') as f:
        return f.read().strip()

def _write_storefile(path, filename, data):
    """Write a wc file.

    path is the path to the working copy, filename is the name
    of the storefile and data is the data which should be written.
    If data is not empty a trailing \\n character will be added.

    Raises a ValueError if path has no storedir.

    """
    if not _has_storedir(path):
        raise ValueError("path \"%s\" has no storedir" % path)
    fname = _storefile(path, filename)
    tmpfile = None
    try:
        tmpfile = NamedTemporaryFile(dir=_storedir(path), delete=False)
        tmpfile.write(data)
        if data:
            tmpfile.write('\n')
    finally:
        if tmpfile is not None:
            tmpfile.close()
            os.rename(tmpfile.name, fname)

def wc_lock(path):
    """Return a WCLock object.

    path is the path to the working copy.
    The only purpose of this method is to
    "beautify" the following code:

    with wc_lock(path) as lock:
        ...

    """
    return WCLock(path)

def wc_is_project(path):
    """Test if path is a project working copy."""
    missing = missing_storepaths(path, '_apiurl', '_project', '_package')
    if not missing:
        # it is a package dir
        return False
    elif len(missing) == 1 and '_package' in missing:
        return True
    return False

def wc_is_package(path):
    """Test if path is a package working copy."""
    return not missing_storepaths(path, '_apiurl', '_project', '_package')

def wc_read_project(path):
    """Return the name of the project.

    path is the path to the project or package working
    copy.
    If the storefile does not exist or is no file
    a ValueError is raised.

    """
    return _read_storefile(path, '_project')

def wc_read_packages(path):
    """Return the xml data of the _packages file.

    path is the path to the project working copy.
    If the storefile does not exist or is no file
    a ValueError is raised.

    """
    return _read_storefile(path, '_packages')

def wc_read_package(path):
    """Return the name of the package.

    path is the path to the package working copy.
    If the storefile does not exist or is no file
    a ValueError is raised.

    """
    return _read_storefile(path, '_package')

def wc_read_apiurl(path):
    """Return the apiurl for this working copy.

    path is the path to the project or package
    working copy.
    If the storefile does not exist or is no file
    a ValueError is raised.

    """
    return _read_storefile(path, '_apiurl')

def wc_read_files(path):
    """Return the xml data of the _files file.

    path is the path to the package working copy.
    If the storefile does not exist or is no file
    a ValueError is raised.

    """
    return _read_storefile(path, '_files')

def wc_write_apiurl(path, apiurl):
    """Write the _apiurl file.

    path is the path to the working copy and apiurl
    is the apiurl str.

    """
    _write_storefile(path, '_apiurl', apiurl)

def wc_write_project(path, project):
    """Write the _project file.

    path is the path to the working copy and project
    is the name of the project.

    """
    _write_storefile(path, '_project', project)

def wc_write_package(path, package):
    """Write the _package file.

    path is the path to the working copy and package
    is the name of the package.

    """
    _write_storefile(path, '_package', package)

def wc_write_packages(path, xml_data):
    """Write the _packages file.

    path is the path to the project working copy and
    xml_data is the xml str.

    """
    _write_storefile(path, '_packages', xml_data)

def wc_write_files(path, xml_data):
    """Write the _packages file.

    path is the path to the package working copy and
    xml_data is the xml str.

    """
    _write_storefile(path, '_files', xml_data)

def wc_init(path, ext_storedir=None):
    """Initialize path as a working copy.

    path is the path to the new working copy. If path
    does not exist it will be created.
    Raises a ValueError if path is not readable/writable
    or if it is already a working copy or if ext_storedir
    is no dir or is not readable/writable.

    Keyword arguments:
    ext_storedir -- path to an external storedir (default: None).
                    If specified the path/.osc dir is a symlink to
                    ext_storedir.

    """
    if (ext_storedir is not None and
        (not os.path.isdir(ext_storedir) or
         not os.access(ext_storedir, os.W_OK))):
        msg = "ext_storedir \"%s\" is no dir or not writable" % ext_storedir
        raise ValueError(msg)

    storedir = _storedir(path)
    if os.path.exists(storedir):
        raise ValueError("path \"%s\" is already a working copy" % path)
    elif os.path.exists(path) and not os.path.isdir(path):
        raise ValueError("path \"%s\" already exists but is no dir" % path)
    elif not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno != errno.EACCES:
                raise
            raise ValueError("no permission to create path \"%s\"" % path)
    if not os.access(path, os.W_OK):
        msg = "no permission to create a storedir (path: \"%s\")" % path
        raise ValueError(msg)
    if ext_storedir is not None:
        os.symlink(ext_storedir, storedir)
    else:
        os.mkdir(storedir)
    global _PKG_DATA
    data_path = _storefile(path, _PKG_DATA)
    os.mkdir(data_path)
