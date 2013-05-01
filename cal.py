import os
import math
import datetime
import calendar
from urllib import urlencode
from urlparse import urlunparse
from xml.dom import minidom

# from google.appengine.ext import db
# from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from restclient import RESTClient

# import pdb; pdb.Pdb(stdin=sys.__stdin__, stdout=sys.__stdout__).set_trace()
from crypto import encodeData, decodeData


_ = lambda x: os.path.join(os.path.dirname(__file__), 'templates', x)

DOMAIN = 'basecamphq.com'


class TimeEntry(object):
    def __init__(self, hours, description, projectref):
        self.hours = hours
        self.description = description
        self.projectref = projectref


class Day(object):
    styles = ['t1', 't2', 't3', 't4', 't5', 't6', 't7', 't8', 't9']

    def __init__(self, date, time_entries=[]):
        self.day = date
        self.time_entries = sorted(time_entries, key=lambda x: x.projectref)
        # 0 date is a special case
        if not (date >= 0 and date <= 31):
            raise ValueError('%d number is not a day number' % date)

    def __nonzero__(self):
        return self.day

    @property
    def time(self):
        return sum([i.hours for i in self.time_entries])

    @property
    def grouped(self):
        projects = set(map(lambda x: x.projectref[0], self.time_entries))
        grouped = [(x, sum([y.hours
                            for y in self.time_entries
                            if y.projectref[0] == x]
                           )) for x in projects]
        return sorted(grouped)

    def formatted_time(self):
        return '%.2f' % self.time

    @property
    def style(self):
        return "day ttt%.2f" % self.time
        # style = ['day']
        if self.day == 0:
            return 'day prev'
        time = int(math.ceil(self.time))
        if time and time <= 9:
            return 'day ' + self.styles[time - 1]
        elif time:
            return 'day more'
        else:
            return 'day'

    @property
    def color(self):
        return "rgb(%d,%d,%d)" % (
            min([int(self.time / 4.0 * 0xff), 0xff]),
            max([min([int((8.0 - self.time) / 4.0 * 0xff), 0xff]), 0]),
            max([min([int((self.time - 8.0) / 4.0 * 0xff), 0xff]), 0]),
        )

    @property
    def clock(self):
        if not self.time:
            return ''

        def sector(color, time):
            color = "rgb(%d,%d,%d)" % (
                (color >> 16) & 255, (color >> 8) & 255, color & 255)
            trad = math.radians(time / 12.0 * 360)
            x, y = 25 + 25 * math.sin(trad), 25 - 25 * math.cos(trad)
            if time > 6.0:
                cc = "A 25 25 1.57 0 1 25.0 50.0" \
                    " A 25 25 1.57 0 1 %.1f %.1f" % (x, y)
            else:
                cc = "A 25 25 1.57 0 1 %.1f %.1f" % (x, y)
            return "<path fill='%s' d='M 25 25 L 25.00 0.00 %s Z'/>" % (
                color, cc)
        ss = 0.0
        sd = []
        for i, h in self.grouped:
            ss += h
            sd.append(sector(i, ss))
        sd.reverse()
        return "border-color:%s;" \
            "background-image: url(\"data:image/svg+xml;utf8," \
            "<svg height='50' width='50' " \
            "xmlns:xlink='http://www.w3.org/1999/xlink' " \
            "xmlns='http://www.w3.org/2000/svg'>" \
            "<g>%s</g></svg>\");" % (self.color, "".join(sd))


class calRequestHandler(webapp.RequestHandler):
    def __init__(self, *args, **kwargs):
        super(calRequestHandler, self).__init__(*args, **kwargs)

    # absence of this method kills.
    def renderToResponse(self, page_path, values):
        self.response.out.write(template.render(page_path, values))

    def absoluteUrl(self, subdomain, relative_url='', params='', query='',
                    fragment=''):
        if type(query) == dict:
            query = urlencode(query)
        return urlunparse(('https', '%s.%s' % (subdomain, DOMAIN),
                           relative_url, params, query, fragment))


class LoginPage(calRequestHandler):

    def __init__(self, *args, **kwargs):
        super(LoginPage, self).__init__(*args, **kwargs)
        client = RESTClient()
        client.requestHeaders.update({
            'Content-Type': 'application/xml',
            'Accept': 'application/xml'
        })
        self._client = client

    def getSubjectId(self, login, pwd, subdomain):
        """
        Get 'subject_id' for report query - it is id of logged in user.
        """
        self._client.setCredentials(login, pwd)
        self._client.get(self.absoluteUrl(subdomain, '/me.xml'))
        if self._client.status == 200:
            dom = minidom.parseString(self._client.contents)
            return str(dom.getElementsByTagName('id')[0].firstChild.nodeValue)
        else:
            raise Exception('Can\'t get subject_id')

    def get(self):
        self.renderToResponse(_('login.html'), {})

    def post(self):
        login = self.request.get('login')
        pwd = self.request.get('password')
        subdomain = self.request.get('subdomain')

        # check whether all needed data is given
        if not (subdomain and login and pwd):
            self.error(401)
            return

        # make a request to the Basecamp API
        try:
            subject_id = self.getSubjectId(login, pwd, subdomain)
        except:
            self.error(401)
            return

        # save login information in a cookie
        data = [login, pwd, subject_id, subdomain]
        expires = (datetime.datetime.now() + datetime.timedelta(weeks=2))\
            .strftime('%a, %d-%b-%Y %H:%M:%S UTC')
        ssid_cookie = 'ssid=%s; expires=%s' % \
            (encodeData(tuple(data)), expires)
        self.response.headers.add_header('Set-Cookie', str(ssid_cookie))

        # save value of 'Remember me' checkbox in a cookie
        saveuser = self.request.get('saveuser', 'off').lower()
        saveuser = saveuser == 'on' and True or False
        if not saveuser:
            nosave_cookie = 'nosave=1; expires=%s' % expires
            self.response.headers.add_header('Set-Cookie', str(nosave_cookie))


class LogoutPage(calRequestHandler):

    def __init__(self, *args, **kwargs):
        super(LogoutPage, self).__init__(*args, **kwargs)

    def get(self):
        self.post()

    def post(self):
        ssid = self.request.cookies.get('ssid', '')
        data = decodeData(ssid)
        if not data:
            self.redirect('/login')
            return
        self.response.headers['Set-Cookie'] = str(
            'ssid=%s; expires=Fri, 31-Dec-2008 23:59:59 GMT;' % ssid)
        self.renderToResponse(_('logout.html'), {})


class MainPage(calRequestHandler):

    def __init__(self, *args, **kwargs):
        super(MainPage, self).__init__(*args, **kwargs)
        client = RESTClient()
        client.requestHeaders.update({
            'Content-Type': 'application/xml',
            'Accept': 'application/xml'
        })
        self._client = client

    def get(self):
        self.post()

    def post(self):
        isSessioned = False
        subdomain = None

        if 'ssid' in self.request.cookies:
            data = decodeData(self.request.cookies['ssid'])
            if data:
                isSessioned = True
                login, pwd, subjectId = data[:3]
                if len(data) > 3:
                    subdomain = data[3]

        if not isSessioned:
            self.redirect('/login?%s' % urlencode(self.request.str_params))
            return

        saveuser = not self.request.cookies.get('nosave', False)
        if not saveuser:
            ssid_cookie = 'ssid=%s; expires=Fri, 31-Dec-2008 23:59:59 GMT;' % \
                self.request.cookies.get('ssid')
            nosave_cookie = 'nosave=1; expires=Fri, 31-Dec-2008 23:59:59 GMT;'
            self.response.headers.add_header('Set-Cookie', str(ssid_cookie))
            self.response.headers.add_header('Set-Cookie', str(nosave_cookie))

        self._client.setCredentials(
            login,
            pwd,
        )

        project = self.request.get('pf', 'all')
        dt = datetime.datetime.now()
        year = self.request.get('yf', dt.year)
        month = self.request.get('mf', dt.month)
        try:
            project = int(project)
        except:
            project = 'all'
        try:
            year = int(year)
            if year < 2000 or year > 3000:
                raise Exception()
        except:
            year = dt.year
        try:
            month = int(month)
            if month < 1 or month > 12:
                raise Exception()
        except:
            month = dt.month
        dt = dt.replace(month=month, year=year)
        report_raw = self.getMonthTimeReport(
            subdomain, dt.year, dt.month, subjectId, project)
        month_info = []
        report = {'entries': []}
        total_hours = 0
        for week_raw in calendar.monthcalendar(dt.year, dt.month):
            week = []
            month_info.append(week)
            for day in week_raw:
                if day in report_raw[0]:
                    day_obj = Day(day, report_raw[0][day])
                    total_hours += day_obj.time
                    report['entries'].append(day_obj)
                else:
                    day_obj = Day(day)
                week.append(day_obj)

        report_raw[1]['all'] = '-- All projects --'
        # sort projects by a name
        sort_cmp = lambda x, y: cmp(x[1], y[1])
        sorted_projects = sorted(report_raw[1].items(), sort_cmp)
        now = datetime.datetime.now()
        report.update({
            'total_hours': total_hours,
            'weeks': month_info,
            'project_filter': project,
            'year_filter': dt.year,
            'month_filter': dt.month,
            'years': [i + 1 for i in range(now.year - 5, now.year)],
            'projects': sorted_projects,
            'username': login,
            'stayloggedin': saveuser,
            'id': subjectId,
            'root': self.absoluteUrl(subdomain),
            'dt': now,
        })

        values = {
            'report': report,
        }
        self.renderToResponse(_('index.html'), values)

    def getAllProjects(self, subdomain):
        """
        Fetch projects info to resolve ids to names: one general request
        instead of fetching one by one separate projects
        """
        projects_dict = {}
        url = self.absoluteUrl(subdomain, '/projects.xml')
        self._client.get(url)

        project_dom = minidom.parseString(self._client.contents)
        for project in project_dom.getElementsByTagName('projects')[0]\
                .getElementsByTagName('project'):

            id = int(
                project.getElementsByTagName('id')[0].firstChild.nodeValue)
            name = project.getElementsByTagName('name')[0].firstChild.nodeValue
            projects_dict[id] = name
        return projects_dict

    def getMonthTimeReport(self, subdomain, year, month, subject_id,
                           project_filter):

        from_ = '%d%02d01' % (year, month)
        to = '%d%02d%02d' % (
            year, month, max(calendar.monthcalendar(year, month)[-1]))
        report = {}
        projects_dict = None
        url = self.absoluteUrl(subdomain, '/time_entries/report.xml', query={
            'from': from_,
            'to': to,
            'subject_id': subject_id
        })
        # try:
        #    self._client.get(url)
        # except:
        # import pdb; pdb.Pdb(stdin=sys.__stdin__,
        # stdout=sys.__stdout__).set_trace()
        self._client.get(url)
        if self._client.status == 200:
            dom = minidom.parseString(self._client.contents)
            projects_dict = self.getAllProjects(subdomain)

            for time_entry in dom.getElementsByTagName('time-entry'):
                proj_id = int(time_entry.getElementsByTagName(
                    'project-id')[0].firstChild.nodeValue)
                if project_filter != 'all' and proj_id != project_filter:
                    continue
                day = time_entry.getElementsByTagName(
                    'date')[0].firstChild.nodeValue
                day = int(day.split('-')[-1])
                hours = time_entry.getElementsByTagName(
                    'hours')[0].firstChild.nodeValue
                hours = float(hours)
                proj_name = projects_dict[proj_id]
                try:
                    description = time_entry.getElementsByTagName(
                        'description')[0].firstChild.nodeValue
                except:
                    description = ''
                entries = report.setdefault(day, [])
                entries.append(
                    TimeEntry(hours, description, (proj_id, proj_name)))
        else:
            raise Exception('Bad HTTP status')
        return (report, projects_dict)


class TestPage(calRequestHandler):

    def __init__(self, *args, **kwargs):
        super(TestPage, self).__init__(*args, **kwargs)
        client = RESTClient()
        client.requestHeaders.update({
            'Content-Type': 'application/xml',
            'Accept': 'application/xml'
        })
        self._client = client

    def get(self):
        self.post()

    def post(self):
        subdomain = None

        project = self.request.get('pf', 'all')
        dt = datetime.datetime.now()
        year = self.request.get('yf', dt.year)
        month = self.request.get('mf', dt.month)
        try:
            year = int(year)
            if year < 2000 or year > 3000:
                raise Exception()
        except:
            year = dt.year
        try:
            month = int(month)
            if month < 1 or month > 12:
                raise Exception()
        except:
            month = dt.month
        dt = dt.replace(month=month, year=year)
        report_raw = self.getMonthTimeReport(
            subdomain, dt.year, dt.month, 0, project)
        month_info = []
        report = {'entries': []}
        total_hours = 0
        for week_raw in calendar.monthcalendar(dt.year, dt.month):
            week = []
            month_info.append(week)
            for day in week_raw:
                if day in report_raw[0]:
                    day_obj = Day(day, report_raw[0][day])
                    total_hours += day_obj.time
                    report['entries'].append(day_obj)
                else:
                    day_obj = Day(day)
                week.append(day_obj)

        report_raw[1]['all'] = '-- All projects --'
        # sort projects by a name
        sort_cmp = lambda x, y: cmp(x[1], y[1])
        sorted_projects = sorted(report_raw[1].items(), sort_cmp)
        now = datetime.datetime.now()
        report.update({
            'total_hours': total_hours,
            'weeks': month_info,
            'project_filter': project,
            'year_filter': dt.year,
            'month_filter': dt.month,
            'years': [i + 1 for i in range(now.year - 5, now.year)],
            'projects': sorted_projects,
            'username': 'test',
            'stayloggedin': False,
            'id': 0,
            'root': self.absoluteUrl(subdomain),
            'dt': now,
        })

        values = {
            'report': report,
        }
        self.renderToResponse(_('index.html'), values)

    def getAllProjects(self, subdomain):
        """
        Fetch projects info to resolve ids to names: one general request
        instead of fetching one by one separate projects
        """
        import random
        projects_dict = dict(
            [(random.randint(0, 256 ** 3), "Project %d" % i)
             for i in range(5)])
        return projects_dict

    def getMonthTimeReport(self, subdomain, year, month, subject_id,
                           project_filter):
        import random
        import string
        # from_ = '%d%02d01' % (year, month)
        # to = '%d%02d%02d' % (year, month, max(calendar.monthcalendar(year,
        # month)[-1]))
        report = {}
        projects_dict = self.getAllProjects(subdomain)

        for i in range(1, 31):
            day = i
            entries = report.setdefault(day, [])
            for r in range(6):
                proj_id = random.choice(projects_dict.keys())
                if project_filter != 'all' and str(proj_id) != project_filter:
                    continue
                proj_name = projects_dict[proj_id]
                description = "".join(random.sample(string.letters, 20))
                hours = 2 * random.random()
                entries.append(
                    TimeEntry(hours, description, (proj_id, proj_name)))
        return (report, projects_dict)

application = webapp.WSGIApplication([
    ('/', MainPage),
    ('/login', LoginPage),
    ('/logout', LogoutPage),
    ('/test', TestPage),
], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
