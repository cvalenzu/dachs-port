"""
Code dealing with the service list.
"""

import os

import gavo
from gavo import config
from gavo import resourcecache
from gavo import sqlsupport
from gavo.parsing import importparser
from gavo.parsing import parseswitch
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.parsing import typeconversion

def makeRecord(publication, service):
	"""returns a record suitable for importing into the service list for the
	publication type of service.
	"""
	rec = {}
	rec["shortName"] = str(service.getMeta("shortName", raiseOnFail=True))
	rec["sourceRd"] = service.rd.sourceId
	rec["internalId"] = service.get_id()
	rec["title"] = (str(service.getMeta("title") or service.getMeta("_title"))
		or rec["shortName"])
	rec["description"] = str(service.getMeta("description") or service.getMeta(
		"_description"))
	rec["renderer"] = publication["render"]
	rec["accessURL"] = "".join([
		config.get("web", "serverURL"),
		config.get("web", "nevowRoot"),
		"/",
		service.rd.sourceId,
		"/",
		service.get_id(),
		"/",
		publication["render"]])
	rec["owner"] = service.get_requiredGroup()
	rec["type"] = publication["type"]
	rec["sets"] = service.getMeta("sets")
	if rec["sets"]:
		rec["sets"] = str(rec["sets"])
	return rec


def getServiceRecsFromRd(rd):
	"""returns all service records defined in the resource descriptor rd.
	"""
	res = []
	for svcId in rd.itemsof_service():
		svc = rd.get_service(svcId)
		for pub in svc.get_publications():
			res.append(makeRecord(pub, svc))
	return res


def updateServiceList(rd):
	"""updates the services defined in rd in the services table in the database.
	"""
	# Don't use resourcecache here since we're going to mess with the rd
	serviceRd = importparser.getRd("__system__/services/services", 
		forImport=True)
	dd = serviceRd.getDataById("servicelist")
	serviceRd.register_property("srcRdId", rd.sourceId)
	inputData = sqlsupport.makeRowsetFromDicts(
		getServiceRecsFromRd(rd), dd.get_Grammar().get_dbFields())
	gavo.ui.silence = True
	dataSet = resource.InternalDataSet(dd, tableMaker=parseswitch.createTable,
		dataSource=inputData)
	dataSet.exportToSql(serviceRd.get_schema())
	gavo.ui.silence = False


def getShortNamesForSets(queriedSets):
	"""returns the list of service shortNames that are assigned to any of
	the set names mentioned in the list queriedSets.
	"""
	dd = resourcecache.getRd("__system__/services/services").getDataById("sets")
	tableDef = dd.getPrimaryRecordDef()
	data = sqlsupport.SimpleQuerier().query(
		"SELECT * FROM %s WHERE setName in %%(sets)s"%(tableDef.get_table()),
		{"sets": queriedSets}).fetchall()
	return [str(r["shortName"]) for r in
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getSetsForService(shortName):
	"""returns the list of set names the service shortName belongs to.
	"""
	dd = resourcecache.getRd("__system__/services/services").getDataById("sets")
	tableDef = dd.getPrimaryRecordDef()
	data = sqlsupport.SimpleQuerier().query(
		"SELECT * FROM %s WHERE shortName = %%(name)s"%(tableDef.get_table()),
		{"name": shortName}).fetchall()
	return [str(r["setName"]) for r in 
		resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows]


def getMatchingServices(whereClause="", pars={}):
	"""queries the services table.
	"""
	dd = resourcecache.getRd("__system__/services/services"
		).getDataById("servicelist")
	return resource.getMatchingData(dd, "services", 
		whereClause, pars).getPrimaryTable()

def queryServicesList(whereClause="", pars={}):
	"""returns the current list of form based services.

	This is mainly for the benefit of the portal page.
	"""
	rd = resourcecache.getRd("__system__/services/services")
	dd = rd.getDataById("services").copy()
	grammar = dd.get_Grammar()
	sources = [f.get_source() for f in grammar.get_items()]
	tables = set([s.split(".")[0] for s in sources])
	if whereClause:
		whereClause = "WHERE "+whereClause
	data = sqlsupport.SimpleQuerier().query(
		"SELECT %s FROM %s %s"%(
			",".join(sources),
			" NATURAL JOIN ".join(tables),
			whereClause), pars).fetchall()
	return resource.InternalDataSet(dd, dataSource=data).getPrimaryTable().rows

resourcecache.makeCache("getWebServiceList", 
	lambda ignored: queryServicesList("srv_interfaces.type='web'"))

def parseCommandLine():
	import optparse
	parser = optparse.OptionParser(usage="%prog [options] [<rd-name>]+")
	parser.add_option("-a", "--all", help="search everything below inputsDir"
		" for publications.", dest="all", action="store_true")
	return parser.parse_args()

def findAllRDs():
	rds = []
	for dir, dirs, files in os.walk(config.get("inputsDir")):
		for file in files:
			if file.endswith(".vord"):
				rds.append(os.path.join(dir, file))
	return rds

def main():
	from gavo import textui
	from gavo.parsing import commandline
	config.setDbProfile("feed")
	opts, args = parseCommandLine()
	if opts.all:
		args = findAllRDs()
	for rdPath in args:
		try:
			updateServiceList(
				importparser.getRd(os.path.join(os.getcwd(), rdPath), 
					forImport=True))
		except Exception, msg:
			commandline.displayError(msg)


if __name__=="__main__":
	from gavo import textui
	import pprint
	config.setDbProfile("querulator")
	pprint.pprint(getShortNamesForSets(["ivo_managed"]))
