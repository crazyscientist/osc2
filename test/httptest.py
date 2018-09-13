import os
from six.moves import cStringIO as StringIO
import unittest
import urllib2
import shutil
from difflib import unified_diff

from osc2.util.io import mkdtemp
from test.xmltest import compare_xml

EXPECTED_REQUESTS = []


class RequestWrongOrder(Exception):
    """raised if an unexpected request is issued to urllib2"""
    def __init__(self, url, exp_url, method, exp_method):
        super(Exception, self).__init__()
        self.url = url
        self.exp_url = exp_url
        self.method = method
        self.exp_method = exp_method

    def __str__(self):
        return '%s, %s, %s, %s' % (self.url, self.exp_url,
                                   self.method, self.exp_method)


class RequestDataMismatch(Exception):
    """raised if POSTed or PUTed data doesn't match with the expected data"""
    def __init__(self, url, got, exp):
        super(Exception, self).__init__()
        self.url = url
        self.got = got
        self.exp = exp

    def __str__(self):
        diff = unified_diff(self.exp.split('\\n'), self.got.split('\\n'))
        # skip diff header
        diff.next()
        diff.next()
        return '%s, %s, %s\nDiff:\n%s' % (self.url, self.got, self.exp,
                                          '\n'.join(diff))


class RequestUnexpectedHeader(Exception):
    """raised if a request contains an unexpected header"""
    def __init__(self, url, hdr, val):
        super(Exception, self).__init__()
        self.url = url
        self.hdr = hdr
        self.val = val

    def __str__(self):
        return "%s: unexpected header %s = %s" % (self.url, self.hdr, self.val)


class RequestHeaderMismatch(Exception):
    """raised if a request's header value mismatches or is not present"""
    def __init__(self, url, hdr, got, exp):
        super(Exception, self).__init__()
        self.url = url
        self.hdr = hdr
        if got is None:
            got = ''
        self.got = got
        self.exp = exp

    def __str__(self):
        return "%s: hdr %s: \'%s\' (got), \'%s\' (expected)" % (self.url,
                                                                self.hdr,
                                                                self.got,
                                                                self.exp)


class MyHeaders(dict):
    """Used to mock a httplib.HTTPMessage object.

    This implementation lacks several methods, but
    this is sufficient for now.

    """
    def getheaders(self, name):
        # e.g. used by cookielib.CookieJar
        val = self.get(name, None)
        if val is None:
            return []
        return [val]


class MyHTTPHandler(urllib2.HTTPHandler, urllib2.HTTPSHandler):
    def __init__(self, *args, **kwargs):
        self._exp_requests = kwargs.pop('exp_requests')
        self._fixtures_dir = kwargs.pop('fixtures_dir')
        # XXX: we can't use super because no class in
        # HTTPHandler's inheritance hierarchy extends object
        urllib2.HTTPHandler.__init__(self, *args, **kwargs)

    def http_open(self, req):
        r = self._exp_requests.pop(0)
        if req.get_full_url() != r[1] or req.get_method() != r[0]:
            raise RequestWrongOrder(req.get_full_url(), r[1], req.get_method(),
                                    r[0])
        if req.get_method() in ('GET', 'DELETE'):
            return self._mock_GET(req, **r[2])
        elif req.get_method() in ('PUT', 'POST'):
            return self._mock_PUT(req, req.get_method(), **r[2])

    https_open = http_open

    def _mock_GET(self, req, **kwargs):
        return self._get_response(req, **kwargs)

    def _mock_PUT(self, req, method, **kwargs):
        exp = kwargs.pop('exp', None)
        if exp is not None and 'expfile' in kwargs:
            raise ValueError('either specify exp or expfile')
        elif 'expfile' in kwargs:
            filename = os.path.join(self._fixtures_dir, kwargs.pop('expfile'))
            exp = open(filename, 'r').read()
        elif exp is None and method == 'PUT':
            # in case of a POST it is ok if no data is posted (for instance
            # if a obs request's state is changed)
            raise ValueError('exp or expfile required')

        content_type = req.get_header('Content-type', '')
        exp_content_type = kwargs.pop('exp_content_type', '')
        if exp_content_type:
            assert content_type == exp_content_type
        data = str(req.get_data())
        if content_type == 'application/xml' and exp is not None:
            if not compare_xml(exp, data):
                raise RequestDataMismatch(req.get_full_url(), exp, data)
        elif exp is not None and data != exp:
            raise RequestDataMismatch(req.get_full_url(), repr(req.get_data()),
                                      repr(exp))
        return self._get_response(req, **kwargs)

    def _get_response(self, req, **kwargs):
        self._check_headers(req, kwargs.pop('exp_headers', {}))
        f = None
        if 'exception' in kwargs:
            raise kwargs['exception']
        if 'text' not in kwargs and 'file' in kwargs:
            filename = os.path.join(self._fixtures_dir, kwargs.pop('file'))
            f = StringIO(open(filename, 'r').read())
        elif 'text' in kwargs and 'file' not in kwargs:
            f = StringIO(kwargs.pop('text'))
        else:
            raise ValueError('either specify text or file')
        code = kwargs.pop('code', 200)
        # everything else in kwargs are response headers
        headers = MyHeaders()
        for k, v in kwargs.iteritems():
            k = k.replace('_', '-')
            headers[k] = v
        resp = urllib2.addinfourl(f, headers, req.get_full_url())
        resp.code = code
        resp.msg = ''
        return resp

    def _check_headers(self, req, headers):
        for hdr, exp_val in headers.iteritems():
            # urllib2 stores the capitalized hdr
            hdr = hdr.capitalize().replace('_', '-')
            val = req.get_header(hdr)
            if val != exp_val:
                if exp_val is not None:
                    raise RequestHeaderMismatch(req, hdr, val, exp_val)
                raise RequestUnexpectedHeader(req, hdr, req.get_header(hdr))


def urldecorator(method, fullurl, **kwargs):
    def decorate(test_method):
        def wrapped_test_method(*args):
            add_expected_request(method, fullurl, **kwargs)
            test_method(*args)
        # "rename" method otherwise we cannot specify a TestCaseClass.testName
        # cmdline arg when using unittest.main()
        wrapped_test_method.__name__ = test_method.__name__
        return wrapped_test_method
    return decorate


def GET(fullurl, **kwargs):
    return urldecorator('GET', fullurl, **kwargs)


def PUT(fullurl, **kwargs):
    return urldecorator('PUT', fullurl, **kwargs)


def POST(fullurl, **kwargs):
    return urldecorator('POST', fullurl, **kwargs)


def DELETE(fullurl, **kwargs):
    return urldecorator('DELETE', fullurl, **kwargs)


def add_expected_request(method, url, **kwargs):
    global EXPECTED_REQUESTS
    EXPECTED_REQUESTS.append((method, url, kwargs))


class MockUrllib2Request(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        dirname = os.path.dirname(__file__)
        fixtures_dir = kwargs.pop('fixtures_dir', os.curdir)
        self._fixtures_dir = os.path.join(dirname, fixtures_dir)
        self._orig_build_opener = None
        super(MockUrllib2Request, self).__init__(*args, **kwargs)

    def fixture_file(self, *paths):
        path = os.path.join(self._tmp_fixtures, *paths)
        return os.path.abspath(path)

    def setUp(self):
        global EXPECTED_REQUESTS
        super(MockUrllib2Request, self).setUp()
        EXPECTED_REQUESTS = []
        self._orig_build_opener = urllib2.build_opener

        def build_opener(*handlers):
            handlers += (MyHTTPHandler(exp_requests=EXPECTED_REQUESTS,
                                       fixtures_dir=self._fixtures_dir), )
            return self._orig_build_opener(*handlers)
        urllib2.build_opener = build_opener
        self._tmp_dir = mkdtemp(prefix='osc_test')
        self._tmp_fixtures = os.path.join(self._tmp_dir, 'fixtures')
        shutil.copytree(self._fixtures_dir, self._tmp_fixtures, symlinks=True)

    def tearDown(self):
        super(MockUrllib2Request, self).tearDown()
        shutil.rmtree(self._tmp_dir)
        self.assertTrue(len(EXPECTED_REQUESTS) == 0)
        # _orig_build_opener should never be None
        if self._orig_build_opener is not None:
            urllib2.build_opener = self._orig_build_opener
