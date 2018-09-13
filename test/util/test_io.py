import unittest
import os
import sys
import tempfile
from six.moves import cStringIO as StringIO

from osc2.util.io import TemporaryDirectory, mkdtemp, mkstemp
from test.osctest import OscTestCase


def suite():
    return unittest.makeSuite(TestIO)


class TestIO(OscTestCase):
    def setUp(self):
        # in order to avoid race conditions, all tmpdirs are created
        # in a testcase specific tmpdir (actually, we cannot avoid race
        # conditions, because another process could write into our tmpdir
        # for whatever reason... but this is so unlikely:))
        self._tmpdir = tempfile.mkdtemp(suffix='testio')

    def tearDown(self):
        # if the tmpdir is not empty, a testcase failed;
        # so it does not harm if rmdir bails out as well
        # (using shutil is too "dangerous")
        os.rmdir(self._tmpdir)

    def test_tmpdir1(self):
        """simple temporary directory"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        path = tmpdir.path
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))
        self.assertEqual(str(tmpdir), path)
        # a simple assignment to path is not supposed to work, but _path
        # can still be modified (_never_ do that)
        self.assertRaises(AttributeError, setattr, tmpdir, 'path', path)
        tmpdir.rmtree()
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir2(self):
        """simple temporary directory (remove with rmdir)"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        path = tmpdir.path
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))
        tmpdir.rmdir()
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir3(self):
        """multiple remove"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        path = tmpdir.path
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))
        tmpdir.rmtree()
        self.assertFalse(os.path.isdir(path))
        # a call to path does not recreate the tmpdir
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(path))
        # recreate directory
        os.mkdir(path)
        self.assertTrue(os.path.isdir(path))
        # subsequent rmdir/rmtree calls have no affect anymore
        tmpdir.rmdir()
        tmpdir.rmtree()
        self.assertTrue(os.path.isdir(path))
        os.rmdir(path)

    def test_tmpdir4(self):
        """test __del__ method"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        path = tmpdir.path
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))
        del tmpdir
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir5(self):
        """test advanced __del__ semantics"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        ref = tmpdir
        path = tmpdir.path
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))
        # ref still references the TemporaryDirectory object
        del tmpdir
        self.assertTrue(os.path.isdir(path))
        del ref
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir6(self):
        """test context manager"""
        path = None
        with TemporaryDirectory(dir=self._tmpdir) as tmpdir:
            path = tmpdir.path
            self.assertTrue(os.path.isdir(path))
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir7(self):
        """test context manager (double cleanup has no effect)"""
        path = None
        with TemporaryDirectory(dir=self._tmpdir) as tmpdir:
            path = tmpdir.path
            self.assertTrue(os.path.isdir(path))
        self.assertIsNone(tmpdir.path)
        self.assertFalse(os.path.isdir(path))
        # also performs a rmtree
        del tmpdir

    def test_tmpdir8(self):
        """test context manager (delete=False)"""
        path = None
        with TemporaryDirectory(dir=self._tmpdir, delete=False) as tmpdir:
            path = tmpdir.path
            self.assertTrue(os.path.isdir(path))
        self.assertTrue(os.path.isdir(path))
        self.assertIsNotNone(tmpdir.path)
        del tmpdir
        self.assertTrue(os.path.isdir(path))
        os.rmdir(path)

    def test_tmpdir9(self):
        """test __enter__ (tmpdir was already deleted)"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        tmpdir.rmtree()
        self.assertIsNone(tmpdir.path)
        self.assertRaises(ValueError, tmpdir.__enter__)

    def test_tmpdir10(self):
        """do not remove tmpdir"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir, delete=False)
        path = tmpdir.path
        self.assertTrue(os.path.isdir(path))
        del tmpdir
        self.assertTrue(os.path.isdir(path))
        os.rmdir(path)

    def test_tmpdir11(self):
        """test remove nonempty dir with rmdir=True"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir, rmdir=True)
        path = tmpdir.path
        self.assertTrue(os.path.isdir(path))
        fname = os.path.join(path, 'foo')
        with open(fname, 'w'):
            pass
        self.assertTrue(os.path.exists(fname))
        self.assertRaises(OSError, tmpdir.__del__)
        self.assertTrue(os.path.exists(fname))
        os.unlink(fname)
        del tmpdir
        self.assertFalse(os.path.isdir(path))

    def test_tmpdir12(self):
        """test manual removal of the tmpdir"""
        tmpdir = TemporaryDirectory(dir=self._tmpdir)
        path = tmpdir.path
        self.assertTrue(os.path.exists(path))
        os.rmdir(path)
        self.assertFalse(os.path.exists(path))
        # as long as the directory is gone, we are fine
        tmpdir.rmdir()

    def test_tmpdir13(self):
        """test __del__ method with module unloading"""
        # avoid an unraised exception:
        # Exception AttributeError: "'NoneType' object has no attribute 'path'"
        # in <bound method TemporaryDirectory.__del__ of
        # <osc2.util.io.TemporaryDirectory object at 0x7f8abc8d7910>> ignored
        #
        # This exception was "raised" in the TemporaryDirectory.__del__ method,
        # if the "osc2.util.io" was already "unloaded" (the __del__ method
        # calls the _cleanup method, which tried to call the
        # os.path.isdir function).
        # What happened is the following:
        # If the "osc2.util.io" module is passed to _PyModule_Clear
        # (Objects/moduleobject.c), almost all entries in the module dict are
        # set to None. That is, the entry for the key "os" points to None.
        # Now, suppose that there is still a TemporaryDirectory instance
        # around, whose __del__ method is eventually called. During this call,
        # "os" resolves to None and therefore the subsequent lookup for the
        # name "path" leads to the AttributeError.
        # Instead of raising this exception, it is just printed to stderr,
        # because it occurred in a __del__ method (see slot_tp_del
        # (Objects/typeobject.c) and PyErr_WriteUnraisable (Python/errors.c)).

        # avoid fiddling with sys.modules in the "main" process
        pid = os.fork()
        if pid == 0:
            ret = os.EX_SOFTWARE
            try:
                sio = StringIO()
                sys.stderr = sio
                tmpdir = TemporaryDirectory(dir=self._tmpdir)
                tmpdir.path
                # clean tmpdir manually, because del tmpdir could
                # raise an exception
                os.rmdir(tmpdir.path)
                del sys.modules['osc2.util.io']
                del sys.modules['osc2.util']
                del sys.modules['osc2']
                del tmpdir
                self.assertEqual(sio.getvalue(), '')
                ret = os.EX_OK
            finally:
                os._exit(ret)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(status, os.WEXITSTATUS(os.EX_OK))

    def test_mkdtemp1(self):
        """simple mkdtemp test"""
        tmpdir = mkdtemp(dir=self._tmpdir)
        self.assertTrue(os.path.isdir(tmpdir))
        tmpdir.rmtree()
        self.assertFalse(os.path.isdir(tmpdir))

    def test_mkdtemp2(self):
        """simple mkdtemp (remove with rmdir)"""
        tmpdir = mkdtemp(dir=self._tmpdir)
        self.assertTrue(os.path.isdir(tmpdir))
        tmpdir.rmdir()
        self.assertFalse(os.path.isdir(tmpdir))

    def test_mkdtemp3(self):
        """test __del__ method"""
        tmpdir = mkdtemp(dir=self._tmpdir)
        self.assertTrue(os.path.isdir(tmpdir))
        path = str(tmpdir)
        del tmpdir
        self.assertFalse(os.path.isdir(path))

    def test_mkdtemp4(self):
        """advanced __del__ semantics"""
        tmpdir = mkdtemp(dir=self._tmpdir)
        self.assertTrue(os.path.isdir(tmpdir))
        path = str(tmpdir)
        ref = tmpdir
        # ref still references the tmpdir, so the
        # actual object is not deleted
        del tmpdir
        self.assertTrue(os.path.isdir(path))
        del ref
        self.assertFalse(os.path.isdir(path))

    def test_mkdtemp5(self):
        """test suffix and str operations"""
        tmpdir = mkdtemp(dir=self._tmpdir, suffix='foo')
        self.assertTrue(tmpdir.endswith('foo'))
        os.path.join(tmpdir, 'test')
        # test more str operations
        tmpdir + 'foo'
        'foo' + tmpdir
        self.assertTrue(len(tmpdir) > 0)
        self.assertTrue('foo' in tmpdir)
        self.assertEqual(''.join(tmpdir), tmpdir)
        # stat requires a "real" str (that is a str/unicode or buffer instance)
        os.stat(tmpdir)

    def test_mkdtemp6(self):
        """test context manager"""
        with mkdtemp(dir=self._tmpdir) as tmpdir:
            self.assertTrue(os.path.isdir(tmpdir))
        self.assertFalse(os.path.isdir(tmpdir))

    def test_mkstemp1(self):
        """test simple mkstemp"""
        tmpfile = mkstemp(dir=self._tmpdir)
        self.assertTrue(os.path.isfile(tmpfile))
        self.assertEqual(tmpfile.name, tmpfile)
        self.assertIsNotNone(os.stat(tmpfile))
        tmpfile.close()
        self.assertFalse(os.path.isfile(tmpfile))

    def test_mkstemp2(self):
        """test context manager"""
        with mkstemp(dir=self._tmpdir) as tmpfile:
            self.assertTrue(os.path.isfile(tmpfile))
        self.assertFalse(os.path.isfile(tmpfile))

    def test_mkstemp3(self):
        """write to tmpfile"""
        with mkstemp(dir=self._tmpdir) as tmpfile:
            tmpfile.write('foobar')
            tmpfile.flush()
            with open(tmpfile, 'r') as f:
                self.assertEqual(f.read(), 'foobar')
        self.assertFalse(os.path.isfile(tmpfile))

if __name__ == '__main__':
    unittest.main()
