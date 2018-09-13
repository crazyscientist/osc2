"""Provides a base class for doing http requests and a sample implementation
based on urllib2.

Example usage:
 logger = logging.StreamHandler()
 logger.setLevel(logging.DEBUG)
 logging.getLogger('httprequest').addHandler(ch)
 logging.getLogger('httprequest').setLevel(logging.DEBUG)
 r = Urllib2HTTPRequest('https://host', username='user', password='pass')
 f = r.get('/source/home:Marcus_H/_meta', schema='/path/to/schema.(rng|xsd)')
 print f.read()
"""

import base64
import logging
import mmap

import os
import six
from lxml import etree
from six.moves import cStringIO
from six.moves import urllib_request, urllib_error, urllib_parse
from six.moves.http_cookiejar import LWPCookieJar
from six.moves.urllib.parse import urlsplit, urlunsplit

if six.PY2:
    from urllib2 import AbstractHTTPHandler
else:
    from urllib.request import AbstractHTTPHandler

__all__ = ['AbstractHTTPRequest', 'AbstractHTTPResponse', 'HTTPError',
           'Urllib2HTTPResponse', 'Urllib2HTTPError', 'Urllib2HTTPRequest']


def build_url(apiurl, path, **query):
    """Returns an url str.

    apiurl has the form <protocol>://host and path is the path.

    This method should be used by all methods which need to construct
    an url manually.

    Keyword arguments:
    **query -- optional query parameters (default: {})

    """
    quoted_path = '/'.join([urllib_parse.quote_plus(p) for p in path.split('/')])
    # rewrite to internal key -> ['val'] representation
    query.update([(k, [query[k]]) for k in query.keys()
                  if not hasattr(query[k], 'pop')])
    # sort query keys (to get a reproduceable url)
    sorted_keys = sorted(query.keys())
    quoted_query = '&'.join([urllib_parse.quote_plus(k) + '=' +
                             urllib_parse.quote_plus(v)
                             for k in sorted_keys for v in query[k] if v])
    scheme, host = urlsplit(apiurl)[0:2]
    return urlunsplit((scheme, host, quoted_path, quoted_query,
                       ''))


class AbstractHTTPResponse(object):
    """Base class for an http response object.

    It provides the following attributes:

    """

    def __init__(self, url, code, headers, orig_resp=None):
        """Constructs a new object.

        Arguments:
        url -- the url of the request
        code -- the http status code (int)
        headers -- a dict which contains the headers

        Keyword arugments:
        orig_resp -- the original response object (default: None)

        """
        super(AbstractHTTPResponse, self).__init__()
        self.url = url
        self.code = code
        self.headers = headers
        self.orig_resp = orig_resp

    def read(self, size=-1):
        """Read the response.

        If size is specified read size bytes (by default size is -1
        so everything will be read).

        """
        raise NotImplementedError()

    def close(self):
        """Close the connection/files.

        Subsequent reads are not guaranteed to succeed (depends on
        the implementation).

        """
        raise NotImplementedError()


class HTTPError(Exception):
    """Raised if a http error occured.

    It is simply a wrapper for the implementation specific exception.

    """

    def __init__(self, url, code, headers, orig_exc=None):
        """Constructs a new HTTPError object.

        Arguments:
        url -- the url of the request
        code -- the http status code (int)
        headers -- a dict which contains the headers (if present)

        Keyword arguments:
        orig_exc -- the original exception (default: None)

        """
        super(HTTPError, self).__init__((), str(orig_exc))
        self.url = url
        self.code = code
        self.headers = headers
        self.orig_exc = orig_exc


class AbstractHTTPRequest(object):
    """Base class which provides methods for doing http requests.

    All parameters passed to the methods which make up the url will be quoted
    before issuing the request.
    There are 2 ways of passing a query parameter:
    - key=val or
    - key=['val1', ..., 'valn'] if a query parameter is used more than once
    Additionally if val is the empty str or None the complete query parameter
    is ignored.

    """

    def __init__(self, apiurl, validate=False):
        """Constructs a new object.

        apiurl is the target location for each request. It is a str which
        consists of a scheme and host and an optional port, for example
        http://example.com.
        Keyword arguments:
        validate -- if True xml response will be validated (if a schema was
                    specifed) (default False)

        """
        super(AbstractHTTPRequest, self).__init__()
        self.apiurl = apiurl
        self.validate = validate

    def get(self, path, apiurl='', schema='', **query):
        """Issues a http request to apiurl/path.

        The path parameter specified the path of the url.
        Keyword arguments:
        apiurl -- use this url instead of the default apiurl
        schema -- path to schema file (default '')
        query -- optional query parameters

        """
        raise NotImplementedError()

    def put(self, path, data=None, filename='', apiurl='', content_type='',
            schema='', **query):
        """Issues a http PUT request to apiurl/path.

        Either data or file mustn't be None.
        Keyword arguments:
        data -- a str or file-like object which should be PUTed (default None)
        filename -- path to a file which should be PUTed (default None)
        apiurl -- use this url instead of the default apiurl
        content_type -- use this value for the Content-type header
        schema -- path to schema file (default '')
        query -- optional query parameters

        """
        raise NotImplementedError()

    def post(self, path, data=None, filename='', urlencoded=False, apiurl='',
             content_type='', schema='', **query):
        """Issues a http POST request to apiurl/path.

        Either data or file mustn't be None.
        A ValueError is raised if content_type and urlencoded is specified.
        Keyword arguments:
        data -- a str or file-like object which should be POSTed (default None)
        filename -- path to a file which should be POSTed (default None)
        apiurl -- use this url instead of the default apiurl
        content_type -- use this value for the Content-type header
        schema -- path to schema file (default '')
        urlencoded -- used to indicate if the data has to be urlencoded or not;
                      if set to True the requests's Content-Type is
                      'application/x-www-form-urlencoded' (default: False,
                      default Content-Type: 'application/octet-stream')
        query -- optional query parameters

        """
        raise NotImplementedError()

    def delete(self, path, apiurl='', schema='', **query):
        """Issues a http DELETE request to apiurl/path.

        Keyword arguments:
        schema -- path to schema file (default '')
        apiurl -- use this url instead of the default apiurl
        query -- optional query parameters

        """
        raise NotImplementedError()


class Urllib2HTTPResponse(AbstractHTTPResponse):
    """Wraps an urllib2 http response.

    The original response is a urllib.addinfourl object.

    """

    def __init__(self, resp):
        super(Urllib2HTTPResponse, self).__init__(resp.geturl(),
                                                  resp.getcode(),
                                                  resp.info(),
                                                  resp)
        self._sio = None

    def _fobj(self):
        if self._sio is not None:
            return self._sio
        return self.orig_resp

    def read(self, size=-1):
        return self._fobj().read(size)

    def close(self):
        return self._fobj().close()


class Urllib2HTTPError(HTTPError):
    """Wraps an urllib2.HTTPError"""

    def __init__(self, exc):
        super(Urllib2HTTPError, self).__init__(exc.filename, exc.code,
                                               exc.hdrs, exc)


class AbstractUrllib2CredentialsManager(object):
    """Abstract base class for a credentials manager.

    A credentials manager is used to retrieve the credentials
    (username, password) for a given url. Whether the manager
    manages the credentials for just one url or various urls
    is up to the implementation of the concrete subclass.

    """

    def get_credentials(self, url):
        """Returns the credentials for the given url.

        If credentials for passed url exist, a (username, password)
        tuple is returned. Otherwise, the tuple (None, None) is
        returned.

        """
        raise NotImplementedError()


class Urllib2SingleCredentialsManager(AbstractUrllib2CredentialsManager):
    """Manages the credentials for single url."""

    def __init__(self, url, username, password):
        """Constructs a new Urllib2SingleCredentialsManager instance.

        username and password represent the credentials for the
        url url.

        """
        self._password_mgr = urllib_request.HTTPPasswordMgrWithDefaultRealm()
        self._password_mgr.add_password(None, url, username, password)

    def get_credentials(self, url):
        return self._password_mgr.find_user_password(None, url)


class Urllib2BasicAuthHandler(urllib_request.BaseHandler):
    """A default urllib2 basic auth handler.

    It always sends the credentials for the configured url.

    """
    AUTH_HEADER = 'Authorization'

    def __init__(self, creds_mgr):
        """Constructs a new Urllib2BasicAuthHandler object.

        creds_mgr is an instance of a subclass of the class
        AbstractUrllib2CredentialsManager.

        """
        self._creds_mgr = creds_mgr

    def http_request(self, request):
        if not request.has_header(self.AUTH_HEADER):
            url = request.get_full_url()
            user, password = self._creds_mgr.get_credentials(url)
            if user is not None and password is not None:
                creds = base64.b64encode("%s:%s" % (user, password))
                auth = "Basic %s" % creds
                request.add_unredirected_header(self.AUTH_HEADER, auth)
        return request

    https_request = http_request


class Urllib2HTTPRequest(AbstractHTTPRequest):
    """Do http requests with urllib2.

    Basically this class just delegates the requests to urllib2. It also
    supports basic auth authentification.

    """

    def __init__(self, apiurl, validate=False, username='', password='',
                 cookie_filename='', debug=False, mmap=True,
                 mmap_fsize=1024 * 512, handlers=None):
        """constructs a new Urllib2HTTPRequest object.

        apiurl is the url which is used for every request.
        Keyword arguments:
        validate -- global flag to control validation (if set to False no
                    response validation is done - even if a schema file
                    was specified) (default False)
        username -- username which is used for basic authentification
                    (default '')
        password -- password which is used for basic authentification
                    (default '')
        debug -- log debug messages
        mmap -- use mmap when POSTing or PUTing a file (default True)
        mmap_fsize -- specifies the minimum filesize for using mmap
                      (default 1024*512)
        handlers -- list of additional urllib2 handlers (default None)

        """
        super(Urllib2HTTPRequest, self).__init__(apiurl, validate)
        self.debug = debug
        self._use_mmap = mmap
        self._mmap_fsize = mmap_fsize
        self._logger = logging.getLogger(__name__)
        self._install_opener(username, password, cookie_filename, handlers)

    def _install_opener(self, username, password, cookie_filename, handlers):
        if handlers is None:
            handlers = []
        cookie_processor = self._setup_cookie_processor(cookie_filename)
        if cookie_processor is not None:
            handlers.append(cookie_processor)
        authhandler = self._setup_authhandler(username, password)
        if authhandler is not None:
            handlers.append(authhandler)
        if self.debug:
            AbstractHTTPHandler.__init__ = (
                lambda self, debuglevel=0: setattr(self, '_debuglevel', 1))
        opener = urllib_request.build_opener(*handlers)
        urllib_request.install_opener(opener)

    def _setup_cookie_processor(self, cookie_filename):
        if not cookie_filename:
            return None
        if (os.path.exists(cookie_filename) and not
        os.path.isfile(cookie_filename)):
            raise ValueError("%s exists but is no file" % cookie_filename)
        elif not os.path.exists(cookie_filename):
            open(cookie_filename, 'w').close()
        cookiejar = LWPCookieJar(cookie_filename)
        cookiejar.load(ignore_discard=True)
        return urllib_request.HTTPCookieProcessor(cookiejar)

    def _setup_authhandler(self, username, password):
        if username == '':
            return None
        creds_mgr = Urllib2SingleCredentialsManager(self.apiurl, username,
                                                    password)
        return Urllib2BasicAuthHandler(creds_mgr)

    def _build_request(self, method, path, apiurl, **query):
        if not apiurl:
            apiurl = self.apiurl
        url = build_url(apiurl, path, **query)
        request = urllib_request.Request(url)
        request.get_method = lambda: method
        return request

    def _validate_response(self, resp, schema_filename):
        if not schema_filename or not self.validate:
            return False
        # this is needed for validation so that we can seek to the "top" of
        # the file again (after validation)
        sio = cStringIO(resp.read())
        resp._sio = sio
        self._logger.debug("validate resp against schema: %s", schema_filename)
        root = etree.fromstring(resp.read())
        resp._sio.seek(0, os.SEEK_SET)
        if schema_filename.endswith('.rng'):
            schema = etree.RelaxNG(file=schema_filename)
        elif schema_filename.endswith('.xsd'):
            schema = etree.XMLSchema(file=schema_filename)
        else:
            raise ValueError('unsupported schema file')
        schema.assertValid(root)
        return True

    def _new_response(self, resp):
        return Urllib2HTTPResponse(resp)

    def _send_request(self, method, path, apiurl, schema, **query):
        request = self._build_request(method, path, apiurl, **query)
        self._logger.info(request.get_full_url())
        try:
            f = urllib_request.urlopen(request)
        except urllib_error.HTTPError as e:
            raise Urllib2HTTPError(e)
        f = self._new_response(f)
        self._validate_response(f, schema)
        return f

    def _send_data(self, request, data, filename, content_type, schema,
                   urlencoded):
        self._logger.info(request.get_full_url())
        f = None
        if content_type and urlencoded:
            msg = 'content_type and urlencoded are mutually exclusive'
            raise ValueError(msg)
        if content_type:
            request.add_header('Content-type', content_type)
        elif urlencoded:
            request.add_header('Content-type',
                               'application/x-www-form-urlencoded')
        else:
            request.add_header('Content-type', 'application/octet-stream')
        try:
            if filename:
                f = self._send_file(request, filename, urlencoded)
            else:
                if urlencoded:
                    data = urllib_parse.quote_plus(data)
                f = urllib_request.urlopen(request, data)
        except urllib_error.HTTPError as e:
            raise Urllib2HTTPError(e)
        f = self._new_response(f)
        self._validate_response(f, schema)
        return f

    def _send_file(self, request, filename, urlencoded):
        with open(filename, 'rb') as fobj:
            fsize = os.path.getsize(filename)
            if self._use_mmap and fsize >= self._mmap_fsize and not urlencoded:
                self._logger.debug("using mmap for file: %s" % filename)
                data = mmap.mmap(fobj.fileno(), fsize, mmap.MAP_SHARED,
                                 mmap.PROT_READ)
                data = buffer(data)
            else:
                data = fobj.read()
            if urlencoded:
                data = urllib_parse.quote_plus(data)
            return urllib_request.urlopen(request, data)

    def _check_put_post_args(self, data, filename):
        if filename and data is not None:
            raise ValueError("either specify file or data but not both")
        elif filename and not os.path.isfile(filename):
            raise ValueError("filename %s does not exist" % filename)

    def get(self, path, apiurl='', schema='', **query):
        return self._send_request('GET', path, apiurl, schema, **query)

    def delete(self, path, apiurl='', schema='', **query):
        return self._send_request('DELETE', path, apiurl, schema, **query)

    def put(self, path, data=None, filename='', apiurl='', content_type='',
            schema='', **query):
        self._check_put_post_args(data, filename)
        request = self._build_request('PUT', path, apiurl, **query)
        return self._send_data(request, data, filename, content_type,
                               schema, False)

    def post(self, path, data=None, filename='', apiurl='', content_type='',
             schema='', urlencoded=False, **query):
        self._check_put_post_args(data, filename)
        request = self._build_request('POST', path, apiurl, **query)
        return self._send_data(request, data, filename, content_type,
                               schema, urlencoded)
