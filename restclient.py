"""Simple REST Client for using by Basecamp API wrapper


"""

import httplib
import urllib
import urlparse
import base64


def isRelativeURL(url):
    """Determines whether the given URL is a relative path segment
    """
    pieces = urlparse.urlparse(url)
    if not pieces[0] and not pieces[1]:
        return True
    return False

def absoluteURL(base, url):
    """Converts a URL to an absolute URL given a base
    """
    if not isRelativeURL(url):
        return url

    pieces = list(urlparse.urlparse(base))
    urlPieces = list(urlparse.urlparse(url))

    if not pieces[2].endswith('/'):
        pieces[2] += '/'
    pieces[2] = urlparse.urljoin(pieces[2], urlPieces[2])

    if urlPieces[4]:
        if pieces[4]:
            pieces[4] = pieces[4] + '&' + urlPieces[4]
        else:
            pieces[4] = urlPieces[4]

    return urlparse.urlunparse(pieces)


def getFullPath(pieces, params):
    """Build a full httplib request path, including a query string
    """
    query = ''
    if pieces[4]:
        query = pieces[4]
    if params:
        encParams = urllib.urlencode(params)
        if query:
            query += '&' + encParams
        else:
            query = encParams
    return urlparse.urlunparse(
        ('', '', pieces[2], pieces[3], query, pieces[5]))


class RESTClient(object):

    connectionFactory = httplib.HTTPConnection
    sslConnectionFactory = httplib.HTTPSConnection

    def __init__(self, url=None):
        self.requestHeaders = {}
        self._reset()
        self._requestData = None
        self.url = ''
        if url:
            self.open(url)

    @property
    def fullStatus(self):
        return '%i %s' % (self.status, self.reason)

    def _reset(self):
        self.headers = []
        self.contents = {}
        self.status = None
        self.reason = None

    def open(self, url='', data=None, params=None, headers=None, method='GET'):
        # Create a correct absolute URL and set it.
        self.url = absoluteURL(self.url, url)

        # Create the full set of request headers
        requestHeaders = self.requestHeaders.copy()
        if headers:
            requestHeaders.update(headers)

        # Let's now reset all response values
        self._reset()

        # Store all the request data
        self._requestData = (url, data, params, headers, method)

        # Make a connection and retrieve the result
        pieces = urlparse.urlparse(self.url)
        if pieces[0] == 'https':
            connection = self.sslConnectionFactory(pieces[1])
        else:
            connection = self.connectionFactory(pieces[1])
        try:
            connection.request(
                method, getFullPath(pieces, params), data, requestHeaders)
            response = connection.getresponse()
        except Exception, e:
            connection.close()
            self.status, self.reason = e.args
            raise e
        else:
            self.headers = response.getheaders()
            self.contents = response.read()
            self.status = response.status
            self.reason = response.reason
            connection.close()

    def get(self, url='', params=None, headers=None):
        self.open(url, None, params, headers)

    def put(self, url='', data='', params=None, headers=None):
        self.open(url, data, params, headers, 'PUT')

    def post(self, url='', data='', params=None, headers=None):
        self.open(url, data, params, headers, 'POST')

    def delete(self, url='', params=None, headers=None):
        self.open(url, None, params, headers, 'DELETE')

    def setCredentials(self, username, password):
        creds = username + u':' + password
        creds = "Basic " + base64.encodestring(creds.encode('utf-8')).strip()
        self.requestHeaders['Authorization'] = creds

    def reload(self):
        self.open(*self._requestData)

