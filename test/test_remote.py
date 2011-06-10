import unittest

from lxml import etree

from osc.remote import RemoteProject, RemotePackage
from osctest import OscTest
from httptest import GET, PUT, POST, DELETE, MockUrllib2Request

class TestRemoteModel(OscTest):
    def __init__(self, *args, **kwargs):
        kwargs['fixtures_dir'] = 'test_remote_fixtures'
        super(TestRemoteModel, self).__init__(*args, **kwargs)

    @GET('http://localhost/source/foo/_meta', file='project.xml')
    def test_project1(self):
        """get a remote project"""
        prj = RemoteProject.find('foo')
        self.assertEqual(prj.title, 'just a dummy title')
        self.assertEqual(prj.description, 'This is a detailed and more' \
                                          ' lengthy\ndescription of the foo' \
                                          '\nproject.')
        self.assertEqual(prj.repository.get('name'), 'openSUSE_Factory')
        self.assertEqual(prj.repository.path.get('project'),
                         'openSUSE:Factory')
        self.assertEqual(prj.repository.path.get('repository'), 'standard')
        self.assertEqual(prj.repository.arch[:], ['x86_64', 'i586'])
        self.assertEqual(prj.person[0].get('userid'), 'testuser')
        self.assertEqual(prj.person[0].get('role'), 'maintainer')
        self.assertEqual(prj.person[1].get('userid'), 'foobar')
        self.assertEqual(prj.person[1].get('role'), 'bugowner')

    @PUT('http://localhost/source/foo/_meta', text='OK', expfile='project.xml')
    def test_project2(self):
        """create a remote project"""
        prj = RemoteProject(name='foo')
        prj.title = 'just a dummy title' 
        prj.description = 'This is a detailed and more lengthy\ndescription' \
                          ' of the foo\nproject.'
        prj.add_person(userid='testuser', role='maintainer')
        prj.add_person(userid='foobar', role='bugowner')
        repo = prj.add_repository(name='openSUSE_Factory')
        repo.add_path(project='openSUSE:Factory', repository='standard')
        repo.add_arch('x86_64')
        repo.add_arch('i586')
        prj.store()

    @GET('http://localhost/source/foo/_meta', file='project.xml')
    @PUT('http://localhost/source/foo/_meta', text='OK',
         expfile='project_modified.xml')
    def test_project3(self):
        """get, modify, store remote project"""
        prj = RemoteProject.find('foo')
        # delete maintainer
        del prj.person[0]
        # delete arch i586
        del prj.repository.arch[1]
        # add additional repo (this time <arch /> first then <path />)
        repo = prj.add_repository(name='openSUSE_11.4')
        repo.add_arch('i586')
        repo.add_path(project='openSUSE:11.4', repository='standard')
        # modify title
        prj.title = 'new title'
        # add + remove illegal tag
        prj.something = 'oops'
        del prj.something
        prj.store()

    @GET('http://localhost/source/test/_meta', file='project_simple.xml')
    @PUT('http://localhost/source/test/_meta', text='OK',
         expfile='project_simple_modified.xml')
    def test_project4(self):
        """test project validation"""
        RemoteProject.SCHEMA = self.fixture_file('project_simple.xsd')
        prj = RemoteProject.find('test')
        prj.person.set('userid', 'bar')
        prj.store()

    @PUT('http://localhost/source/test/_meta', text='<OK />',
         expfile='project_simple_modified.xml')
    def test_project5(self):
        """test project validation"""
        RemoteProject.SCHEMA = self.fixture_file('project_simple.xsd')
        RemoteProject.PUT_RESPONSE_SCHEMA = self.fixture_file('ok_simple.xsd')
        prj = RemoteProject('test')
        prj.add_person(userid='bar', role='maintainer')
        prj.store()

    def test_project6(self):
        """test project validation (invalid model)"""
        RemoteProject.SCHEMA = self.fixture_file('project_simple.xsd')
        prj = RemoteProject('test')
        prj.add_unknown('foo')
        self.assertRaises(etree.DocumentInvalid, prj.validate)
        self.assertRaises(etree.DocumentInvalid, prj.store)

    @GET('http://localhost/source/test/_meta', text='<invalid />')
    def test_project7(self):
        """test project validation (invalid xml response)"""
        RemoteProject.SCHEMA = self.fixture_file('project_simple.xsd')
        self.assertRaises(etree.DocumentInvalid, RemoteProject.find, 'test')

    @PUT('http://localhost/source/test/_meta', text='<INVALID />',
         exp='<project name="test"/>\n')
    def test_project8(self):
        """test project validation 3 (invalid xml response after store)"""
        RemoteProject.SCHEMA = self.fixture_file('project_simple.xsd')
        RemoteProject.PUT_RESPONSE_SCHEMA = self.fixture_file('ok_simple.xsd')
        prj = RemoteProject('test')
        # check that validation is ok
        prj.validate()
        self.assertRaises(etree.DocumentInvalid, prj.store)

    @GET('http://localhost/source/openSUSE%3ATools/osc/_meta',
         file='package.xml')
    def test_package1(self):
        """get a remote package"""
        pkg = RemotePackage.find('openSUSE:Tools', 'osc')
        self.assertEqual(pkg.get('project'), 'openSUSE:Tools')
        self.assertEqual(pkg.get('name'), 'osc')
        self.assertEqual(pkg.title, 'tiny title')
        self.assertEqual(pkg.description, 'some useless\ndescription...')
        self.assertIsNotNone(pkg.debuginfo.disable)
        self.assertIsNotNone(pkg.debuginfo.disable[0])
        self.assertEqual(pkg.debuginfo.enable[0].get('repository'),
                         'openSUSE_Factory')
        self.assertEqual(pkg.debuginfo.enable[1].get('repository'),
                         'some_repo')
        self.assertEqual(pkg.debuginfo.enable[1].get('arch'), 'i586')
        self.assertEqual(pkg.person.get('userid'), 'foobar')
        self.assertEqual(pkg.person.get('role'), 'maintainer')

    @PUT('http://localhost/source/openSUSE%3ATools/osc/_meta', text='OK',
         expfile='package.xml')
    def test_package2(self):
        """create a remote package"""
        pkg = RemotePackage('openSUSE:Tools', 'osc')
        debug = pkg.add_debuginfo()
        debug.add_disable()
        debug.add_enable(repository='openSUSE_Factory')
        debug.add_enable(repository='some_repo', arch='i586')
        pkg.title = 'tiny title'
        pkg.description = 'some useless\ndescription...'
        # modify person afterwards
        person = pkg.add_person(userid='wrongid', role='maintainer')
        person.set('userid', 'foobar')
        pkg.store()

    @GET('http://localhost/source/openSUSE%3ATools/osc/_meta',
         file='package.xml')
    @PUT('http://localhost/source/openSUSE%3ATools/osc/_meta', text='OK',
         expfile='package_modified.xml')
    def test_package3(self):
        """get, modify, store remote package"""
        pkg = RemotePackage.find('openSUSE:Tools', 'osc')
        # remove debuginfo element
        del pkg.debuginfo
        # add build element
        build = pkg.add_build()
        build.add_enable(arch='x86_64')
        build.add_disable(arch='i586')
        # add devel element
        pkg.add_devel(project='openSUSE:Factory', package='osc')
        pkg.store()

    @GET('http://localhost/source/foo/bar/_meta', file='package_simple.xml')
    @PUT('http://localhost/source/newprj/bar/_meta', text='OK',
         expfile='package_simple_modified.xml')
    def test_package4(self):
        """test package validation"""
        RemotePackage.SCHEMA = self.fixture_file('package_simple.xsd')
        pkg = RemotePackage.find('foo', 'bar')
        pkg.set('project', 'newprj')
        pkg.store()

    @PUT('http://localhost/source/newprj/bar/_meta', text='<OK />',
         expfile='package_simple_modified.xml')
    def test_package5(self):
        """test package validation"""
        RemotePackage.SCHEMA = self.fixture_file('package_simple.xsd')
        RemotePackage.PUT_RESPONSE_SCHEMA = self.fixture_file('ok_simple.xsd')
        pkg = RemotePackage('newprj', 'bar')
        pkg.store()

    def test_package6(self):
        """test package validation (invalid model)"""
        RemotePackage.SCHEMA = self.fixture_file('package_simple.xsd')
        pkg = RemotePackage('foo', 'bar')
        pkg.set('invalidattr', 'yes')
        self.assertRaises(etree.DocumentInvalid, pkg.validate)
        self.assertRaises(etree.DocumentInvalid, pkg.store)

    @GET('http://localhost/source/foo/bar/_meta', text='<invalid />')
    def test_package7(self):
        """test package validation (invalid xml response)"""
        RemotePackage.SCHEMA = self.fixture_file('package_simple.xsd')
        self.assertRaises(etree.DocumentInvalid, RemotePackage.find,
                          'foo', 'bar')

    @PUT('http://localhost/source/foo/bar/_meta', text='<INVALID />',
         exp='<package project="foo" name="bar"/>\n')
    def test_package8(self):
        """test package validation (invalid xml response after store)"""
        RemotePackage.SCHEMA = self.fixture_file('package_simple.xsd')
        RemotePackage.PUT_RESPONSE_SCHEMA = self.fixture_file('ok_simple.xsd')
        pkg = RemotePackage('foo', 'bar')
        # check that validation is ok
        pkg.validate()
        self.assertRaises(etree.DocumentInvalid, pkg.store)

if __name__ == '__main__':
    unittest.main()
