import urlparse

from twisted.application import service, internet
from nevow import rend, loaders, appserver

from gavo import config
from gavo import parsing
from gavo import resourcecache
from gavo.web import dispatcher
from gavo.web import htmltable
from gavo.web import product
from gavo.web import resourcebased

parsing.verbose = True
debug = False

class Reloader(rend.Page):
	def locateChild(self, ctx, segments):
		page = dispatcher.ArchiveService()
		return page.locateChild(ctx, segments)

# XXX use port attribute when we can rely on having python 2.5
_serverName = urlparse.urlparse(config.get("web", "serverURL"))[1]
if ":" in _serverName:
	_targetPort = int(_serverName.split(":")[1])
else:
	_targetPort = 80
try:
	_targetPort = int(config.get("web", "serverPort"))
except config.NoOptionError:
	pass
application = service.Application("archive")
if debug:
	mainPage = Reloader()
else:
	mainPage = dispatcher.ArchiveService()

internet.TCPServer(_targetPort, appserver.NevowSite(
	mainPage)).setServiceParent(application)
	
