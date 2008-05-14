"""
Interface to the VO Registry.

Our identifiers have the form

ivo://<authority>/<rd-path>/service-id

for services (do we want specific renderers? That would be bad since right
now they appear as interfaces of the same service...) and

ivo://<authority>/static/<service-resdir-relative-path>

for static resources.

authority is given by authority in the ivoa section of config.
The path of static resources is relative to the rootdir of the services
resource descriptor.
"""

import datetime
import re
import sys
import time
import traceback
import urllib

from mx import DateTime

import gavo
from gavo import ElementTree

from gavo import config
from gavo import meta
from gavo import resourcecache
from gavo import sqlsupport
from gavo import typesystems
from gavo import utils
from gavo.web import servicelist
from gavo.web import staticresource
from gavo.web.registrymodel import OAI, VOR, VOG, DC, RI, VS, SIA, SCS,\
	OAIDC, encoding
from gavo.web.vizierexprs import getSQLKey  # getSQLKey should be moved.


supportedMetadataPrefixes = [
# (prefix, schema-location, namespace)
	("oai_dc", "http://vo.ari.uni-heidelberg.de/docs/schemata/OAI-PMH.xsd",
		"http://www.openarchives.org/OAI/2.0/oai_dc/"),
	("ivo_vor", "http://www.ivoa.net/xml/RegistryInterface/v1.0",
		"http://www.ivoa.net/xml/RegistryInterface/v1.0"),
]

class OAIError(gavo.Error):
	"""is one of the standard OAI errors.
	"""

class BadArgument(OAIError): pass
class BadResumptionToken(OAIError): pass
class BadVerb(OAIError): pass
class CannotDisseminateFormat(OAIError): pass
class IdDoesNotExist(OAIError): pass
class NoRecordsMatch(OAIError): pass
class NoMetadataFormats(OAIError): pass
class NoSetHierarchy(OAIError): pass


_isoTimestampFmt = "%Y-%m-%dT%H:%M:%SZ"


def computeIdentifier(resource):
	"""returns an identifier for resource.

	resource can either be a StaticResource instance, a Service instance
	or a dictionary containing a record from the service table.
	"""
	if isinstance(resource, dict):
		if (resource["sourceRd"]=="<static resource>" or 
				resource["sourceRd"]==servicelist.rdId):
			reskey = "static/%s"%resource["internalId"]
		else:
			reskey = "%s/%s"%(resource["sourceRd"], resource["internalId"])
	elif isinstance(resource, staticresource.StaticResource):
		reskey = "static/%s"%(utils.getRelativePath(resource.srcPath,
			resourcecache.getRd(servicelist.rdId).get_resdir()))
	else:
		reskey = "%s/%s"%(resource.rd.sourceId, resource.get_id())
	return "ivo://%s/%s"%(config.get("ivoa", "authority"), reskey)


def parseIdentifier(identifier):
	"""returns a pair of authority, resource key for identifier.

	Identifier has to be an ivo URI.

	In the context of the gavo DC, the resource key either starts with
	static/ or consists of an RD id and a service ID.
	"""
	mat = re.match("ivo://(\w[^!;:@%$,/]+)/(.*)", identifier)
	if not mat:
		raise IdDoesNotExist(identifier)
	return mat.group(1), mat.group(2)


def getRegistryURL():
	return (config.get("web", "serverURL")+
		config.get("web", "nevowRoot")+"/oai.xml")


def getRegistryDatestamp():
	return time.strftime(_isoTimestampFmt, 
		time.gmtime(
			servicelist.getLastRegistryUpdate()))


def getServiceRecForIdentifier(identifier):
	"""returns the record for identifier in the services table.
	"""
	authority, resKey = parseIdentifier(identifier)
	if resKey.startswith("static/"):
		sourceRd = servicelist.rdId
		internalId = resKey[len("static/"):]
	else:
		parts = resKey.split("/")
		sourceRd = "/".join(parts[:-1])
		internalId = parts[-1]
	matches = servicelist.queryServicesList(
		"sourceRd=%(sourceRd)s AND internalId=%(internalId)s",
		locals(), source="resources")
	if len(matches)!=1:
		raise IdDoesNotExist(identifier)
	return matches[0]


def getResponseHeaders(pars):
	"""returns the OAI response header for a query with pars.
	"""
	return [
		OAI.responseDate[DateTime.now().strftime(_isoTimestampFmt)],
		OAI.request(verb=pars["verb"], 
				metadataPrefix=pars.get("metadataPrefix"))]


def getResourceHeaderTree(rec):
	return OAI.header [
		OAI.identifier[computeIdentifier(rec)],
		OAI.datestamp[rec["dateUpdated"].strftime("%Y-%m-%d")],
		# XXX TODO: The following is extremely inefficient
	][[OAI.setSpec[setSpec] 
		for setSpec in servicelist.getSetsForService(rec["shortName"])]]


def getMetadataNamespace(pars):
	"""returns an object that contains element definitions for resource
	records according to the metadataPrefix item in pars.
	"""
	try:
		return {
			"oai_dc": OAI,
			"ivo_vor": VOR,
		}[pars.get("metadataPrefix", "not_given")]
	except KeyError, md:
		raise CannotDisseminateFormat("%s metadata are not supported"%md)


dateRe = re.compile("\d\d\d\d-\d\d-\d\d$")

def getMatchingRecords(pars):
	"""returns a list of records from the service list matching pars.

	pars is a dictionary mapping any of the following keys to values:

	* from
	* to -- these give a range for which changed records are being returned
	* set -- maps to a sequence of set names to be matched.

	Functions using this probably want to interpret

	* metadataPrefix -- the format the data should be returned in.
	"""
	sqlPars, sqlFrags = {}, []
	if "from" in pars:
		if not dateRe.match(pars["from"]):
			raise BadArgument("from")
		sqlFrags.append("services.dateUpdated >= %%(%s)s"%getSQLKey("from",
			pars["from"], sqlPars))
	if "until" in pars:
		if not dateRe.match(pars["until"]):
			raise BadArgument("until")
		sqlFrags.append("services.dateUpdated <= %%(%s)s"%getSQLKey("until",
			pars["until"], sqlPars))
	if "set" in pars:
		setName = pars["set"]
	else:
		setName = "ivo_managed"
	sqlFrags.append("srv_sets.setName=%%(%s)s"%(getSQLKey("set", 
		setName, sqlPars)))
	try:
		res = servicelist.queryServicesList(
			whereClause=" AND ".join(sqlFrags), pars=sqlPars, source="resSet")
	except sqlsupport.DatabaseError:
		raise BadArgument("Bad syntax in some parameter value")
	except KeyError, msg:
		traceback.print_exc()
		raise gavo.Error("Internal error, missing key: %s"%msg)
	if not res:
		raise NoRecordsMatch()
	return res


_dcBuilder = meta.ModelBasedBuilder([
	('creator', None, [
		('name', meta.stanFactory(DC.creator))]),
	('contributor', None, [
		('name', meta.stanFactory(DC.contributor))]),
	('description', meta.stanFactory(DC.description)),
	('language', meta.stanFactory(DC.language)),
	('rights', meta.stanFactory(DC.rights)),
	('curation', None, [
		('publisher', meta.stanFactory(DC.publisher))]),
	])

def getDCResourceTree(rec):
	service = servicelist.getResourceForRec(rec)
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			OAIDC.dc[
				DC.title[rec["title"]],
				DC.identifier[computeIdentifier(rec)],
				_dcBuilder.build(service),
			]
		]
	]


def getDCResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListRecords[
			[getDCResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]


################ Functions to generate VO Resource elements

def getResourceArgs(rec, service):
	"""returns the mandatory attributes for constructing a Resource record
	for service in a dictionary.
	"""
	return {
		"created": str(service.getMeta("creationDate", 
			default="2000-01-01T00:00:00Z")),
		"updated": rec["dateUpdated"].strftime(_isoTimestampFmt),
		"status": "active",
	}


_contentBuilder = meta.ModelBasedBuilder([
	('subject', meta.stanFactory(VOR.subject)),
	('description', meta.stanFactory(VOR.description)),
	('source', meta.stanFactory(VOR.source)),
	('referenceURL', meta.stanFactory(VOR.referenceURL)),
	('type', meta.stanFactory(VOR.type)),
	('contentLevel', meta.stanFactory(VOR.contentLevel)),
	])

def getResourceItems(resource):
	"""returns a sequence of elements making up a plain VOResource instance. 

	This returns all items up to content, i.e., fills the content model
	of vr:Resource.
	"""
	return [
		VOR.validationLevel(validatedBy=str(resource.getMeta("validatedBy")))[
			resource.getMeta("validationLevel")],
		VOR.title[resource.getMeta("title")],
		VOR.shortName[resource.getMeta("shortName")],
		VOR.identifier[computeIdentifier(resource)],
		VOR.curation[
			VOR.publisher[resource.getMeta("curation.publisher")],
			VOR.creator[
				VOR.name[resource.getMeta("curation.creator.name")],
				VOR.logo[resource.getMeta("curation.creator.logo")],
			],
			VOR.contributor(ivo_id=str(resource.getMeta("contributor.ivo-id")))[
				resource.getMeta("contributor")
			],
			VOR.date[resource.getMeta("date")],
			VOR.version[resource.getMeta("version")],
			VOR.contact[
				VOR.name[resource.getMeta("curation.contact.name", raiseOnFail=True)],
				VOR.address[resource.getMeta("curation.contact.address")],
				VOR.email[resource.getMeta("curation.contact.email")],
				VOR.telephone[resource.getMeta("curation.contact.telephone")],
			],
		],
		VOR.content[
			_contentBuilder.build(resource),
			# XXX TODO: This can't be used yet:
			# VOR.relationship[resource.getMeta("relationship")],
		],
		VOR.rights[
			resource.getMeta("rights"),
		],
	]


def getRegistryResourceTree(rec, resource):
	"""returns a vg:Registry-typed Resource tree for the registry record.

	For now, we only support our own registry, and even there, we might
	be a bit more verbose.

	Most of the meta information is taken from an appropriate rr file.
	"""
	return VOG.Resource(created=str(resource.getMeta("creationDate")),
		status="active", updated=getRegistryDatestamp())[
			getResourceItems(resource),
			VOG.Harvest[
				VOR.description[resource.getMeta("harvest.description")],
				VOG.OAIHTTP(role="std", version="1.0")[
					VOR.accessURL[getRegistryURL()],
				],
				VOG.maxRecords["1000000"],
			],
			VOG.full["false"],
			VOG.managedAuthority[resource.getMeta("managedAuthority")],
		]


def getOrgResourceTree(rec, resource):
	"""returns a vr:Organisation-typed Resource tree for an organization.
	"""
	return VOR.Organisation(**getResourceArgs(rec, resource))[
		getResourceItems(resource),
		VOR.facility[resource.getMeta("facility")],
		VOR.instrument[resource.getMeta("instrument")]]
			

def getAuthResourceTree(rec, resource):
	"""returns a vg:Authority-typed Resource tree.
	"""
	return VOG.Authority(created=str(resource.getMeta("creationDate")),
		status="active", updated=getRegistryDatestamp())[
			getResourceItems(resource),
			VOG.managingOrg[resource.getMeta("managingOrg")],
	]

staticResourceMakers = {
	"authority": (getAuthResourceTree, "authority"),
	"organization": (getOrgResourceTree, "organization"),
	"registry": (getRegistryResourceTree, "registry"),
}

def getResourceMakerForStatic(rec, resource):
	"""returns a function returning a vr metadata tree for a static resource
	record.
	"""
	return staticResourceMakers[str(resource.getMeta("resType"))]


def getResponseTableTree(service):
	return VS.table(role="out")[
		[getTableParamFromField(f)
			for f in service.getOutputFields(None)]
	]


# XXX TODO: Flesh that out
_coverageBuilder = meta.ModelBasedBuilder([
	('coverage', meta.stanFactory(VS.coverage)),
])

def getCatalogServiceItems(service, capabilities):
	"""returns a sequence of elements for a CatalogService based on service
	with capabilities.
	"""
	return getResourceItems(service)+[capabilities]+[
		VOR.facility[ # XXX TODO: maybe look up ivo-ids?
			service.getMeta("facility")],
		VOR.instrument[service.getMeta("instrument")],
		_coverageBuilder.build(service),
		getResponseTableTree(service),
	]
		

def getDataServiceItems(service, capabilities):
	"""returns a sequence of elements for a DataService based on service
	with capabilities.
	"""
	return getResourceItems(service)+[capabilities]+[
		VOR.facility[ # XXX TODO: maybe look up ivo-ids?
			service.getMeta("facility")],
		VOR.instrument[service.getMeta("instrument")],
		_coverageBuilder.build(service),
	]


def getInputParamFromField(dataField, rootElement=VS.param):
	"""returns a InputParam element for dataField.
	"""
	type, length = typesystems.sqltypeToVOTable(dataField.get_dbtype())
	return rootElement[
			VS.name[dataField.get_source()],
			VS.description[dataField.get_description()],
			VS.unit[dataField.get_unit()],
			VS.ucd[dataField.get_ucd()],
			VS.simpleDataType[type]]


def getTableParamFromField(dataField, rootElement=VS.column):
	"""returns a InputParam element for dataField.
	"""
	type, length = typesystems.sqltypeToVOTable(dataField.get_dbtype())
	return rootElement[
			VS.name[dataField.get_source()],
			VS.description[dataField.get_description()],
			VS.unit[dataField.get_unit()],
			VS.ucd[dataField.get_ucd()],
			VS.dataType(arraysize=length)[type]]


def getParamItems(service):
	"""returns a sequence of vs:param elements for the input of service.
	"""
	return [getInputParamFromField(f) for f in service.getInputFields()]

_rendererParameters = {
	"siap.xml":  ("GET",  SIA.interface,  "application/x-votable"),
	"scs.xml":   ("GET",  SCS.interface,  "application/x-votable"),
	"form":      ("POST", VS.ParamHTTP,   "text/html"),
	"upload":    ("POST", VS.ParamHTTP,   "text/html"),
	"mupload":   ("POST", VS.ParamHTTP,   "text/plain"),
	"img.jpeg":  ("POST", VS.ParamHTTP,   "image/jpeg"),
	"mimg.jpeg": ("GET",  VS.ParamHTTP,   "image/jpeg"),
}

def getInterfaceTree(service, renderer):
	qtype, interfaceFactory, resultType = _rendererParameters[renderer]
	use = "full"
	if qtype=="GET":
		use = "base"
	try:
		params = getParamItems(service)
	except Exception, msg:
		# quite a few things can go wrong here.  Since probably nobody cares
		# about these anyway, issue a warning and go on
		gavo.logger.warning("Cannot create parameter items for service %s: %s"%(
			service.getMeta("shortName"), str(msg)))
		params = []
	return interfaceFactory[
		VOR.accessURL(use=use)[service.getURL(renderer, qtype)],
		VOR.securityMethod(standardId=service.getMeta("securityId")),
		VS.resultType[resultType],
		params,
	]


def getSiaCapabilitiesTree(service):
	return SIA.capability[
		getInterfaceTree(service, "siap.xml"),
		SIA.imageServiceType[service.getMeta("sia.type")],
			SIA.maxQueryRegionSize[
				SIA.long[service.getMeta("sia.maxQueryRegionSize.long", default="360")],
				SIA.lat[service.getMeta("sia.maxQueryRegionSize.lat", default="360")],
			],
			SIA.maxImageExtent[
				SIA.long[service.getMeta("sia.maxImageExtent.long", default="360")],
				SIA.lat[service.getMeta("sia.maxImageExtent.lat", default="360")],
			],
			SIA.maxImageSize[
				SIA.long[service.getMeta("sia.maxImageSize.long", default="100000")],
				SIA.lat[service.getMeta("sia.maxImageSize.lat", default="1000000")],
			],
			SIA.maxFileSize[
				service.getMeta("sia.maxFileSize", default="2000000000"),
			],
			SIA.maxRecords[
				service.getMeta("sia.maxRecords", default="200000000"),
			]
		]


def getSiapResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service,
			getSiaCapabilitiesTree(service)),
	]


def getScsResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service,
			getScsCapabilitiesTree(service)),
	]


def getPlainCapabilityTree(service):
	return VOR.capability[  
		# XXX add local description item -- where should this come from?
		getInterfaceTree(service, "form"),
		# XXX local validationLevel???
	]


def getCatalogServiceResourceTree(rec, service):
	return VS.CatalogService(**getResourceArgs(rec, service))[
		getCatalogServiceItems(service, getPlainCapabilityTree(service)),
	]


def getDataServiceResourceTree(rec, service):
	return VS.DataService(**getResourceArgs(rec, service))[
		getDataServiceItems(service, getPlainCapabilityTree(service)),
	]


serviceResourceMakers = {
	"siap.xml": (getSiapResourceTree, "siap"),
	"scs.xml": (getScsResourceTree, "cs"),
}

def getResourceMakerForService(rec, service):
	"""returns a function returning a vr metadata tree for a service.

	The trouble here is that we need to decide on the xsi type of the Resource
	record.  That's trouble because we may in principle have multiple
	conflicting interfaces on a service.  In practice, it's probably not so
	bad (who'd want to look at SIAP output?), so we simply take the first
	renderer matching a standard DAL protocol. 

	However, form renderers probably always count as TableServices,
	so in these cases we simply "upgrade" the default from DataService
	to TableService. XXX TODO: That's rubbish.  What about jpeg, upload?
	"""
	makeResource = getDataServiceResourceTree, "data"
	for pub in service.get_publications():
		if pub["render"] in serviceResourceMakers:
			makeResource = serviceResourceMakers[pub["render"]]
			break
		if pub["render"]=="form":
			makeResource = (getCatalogServiceResourceTree, "tabular")
	return makeResource


def getVOResourceTree(rec):
	"""returns a tree for an individual resource described by the service table
	record rec.

	"""
	resource = servicelist.getResourceForRec(rec)
	if isinstance(resource, staticresource.StaticResource):
		makeResource = getResourceMakerForStatic(rec, resource)
	else:
		makeResource = getResourceMakerForService(rec, resource)
#	sys.stderr.write(">>>> Returning %s service %s\n"%(makeResource[1], 
#		service.getMeta("shortName")))
	return OAI.record[
		getResourceHeaderTree(rec),
		OAI.metadata[
			makeResource[0](rec, resource)
		]
	]


############## End functions to generate VO Resources


def getGetRecordTree(pars, rec, treeGenerator):
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.GetRecord[
			treeGenerator(rec),
		]
	]

def getVOGetRecordTree(pars, rec):
	return getGetRecordTree(pars, rec, getVOResourceTree)

def getDCGetRecordTree(pars, rec):
	return getGetRecordTree(pars, rec, getDCResourceTree)


def getVOResourceListTree(pars):
	return OAI.PMH[
		getResponseHeaders(pars),
# XXX TODO: include standard resources: registry, authority...
		OAI.ListRecords[
			[getVOResourceTree(rec)
				for rec in getMatchingRecords(pars)]]]


def dispatchOnPrefix(pars, OAIBuilder, VORBuilder, *args):
	"""dispatches to OAIBuilder or VORBuilder depending on metadataPrefix.
	"""
	if pars.get("metadataPrefix")=="ivo_vor":
		return VORBuilder(pars, *args)
	elif pars.get("metadataPrefix")=="oai_dc":
		return OAIBuilder(pars, *args)
	else:
		if "metadataPrefix" in pars:
			raise CannotDisseminateFormat("%s metadata are not supported"%pars[
				"metadataPrefix"])
		else:
			raise BadArgument("metadataPrefix missing")


def checkPars(pars, required, optional=[], ignored=set(["verb"])):
	"""raises exceptions for missing or illegal parameters.
	"""
	if "resumptionToken" in pars:
		raise BadResumptionToken(pars["resumptionToken"])
	required, optional = set(required), set(optional)
	for name in pars:
		if name not in ignored and name not in required and name not in optional:
			raise BadArgument(name)
	for name in required:
		if name not in pars:
			raise BadArgument(name)


############## Toplevel tree builders


def getListIdentifiersTree(pars):
	"""returns a tree of registrymodel Elements for a ListIdentifiers response.

	We don't have ivo specific metadata in the headers, so this ignores
	the metadata prefix.
	"""
	checkPars(pars, ["metadataPrefix"], ["from", "until", "set"])
	ns = getMetadataNamespace(pars)
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListIdentifiers[
			[getResourceHeaderTree(rec) for rec in getMatchingRecords(pars)]
		]
	]


def getIdentifyTree(pars):
	"""returns a tree of registrymodel Elements for an Identify response.
	"""
	checkPars(pars, [])
	rec = getServiceRecForIdentifier(
		config.get("ivoa", "registryIdentifier"))
	resource = servicelist.getResourceForRec(rec)
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.Identify[
			OAI.repositoryName["%s publishing registry"%config.get("web",
				"sitename")],
			OAI.baseURL[getRegistryURL()],
			OAI.protocolVersion["2.0"],
			OAI.adminEmail[config.get("operator")],
			OAI.earliestDatestamp["1970-01-01"],
			OAI.deletedRecord["no"],
			OAI.granularity["YYYY-MM-DD"],
			OAI.description[
				getRegistryResourceTree(rec, resource)
			],
		],
	]


def dispatchListRecordsTree(pars):
	"""returns a tree of registrymodel Elements for a ListRecords response.
	"""
	checkPars(pars, ["metadataPrefix"], ["from", "until", "set"])
	return dispatchOnPrefix(pars, getDCResourceListTree,
		getVOResourceListTree)


def dispatchGetRecordTree(pars):
	"""returns a tree of registrymodel Elements for a getRecord response.
	"""
	checkPars(pars, ["identifier", "metadataPrefix"], [])
	identifier = pars["identifier"]
	return dispatchOnPrefix(pars, getDCGetRecordTree,
		getVOGetRecordTree, getServiceRecForIdentifier(identifier))


def getListMetadataFormatTree(pars):
	"""returns a tree of registrymodel Elements for a
	listMetadataFormats response.
	"""
	# identifier is not ignored since crooks may be trying to verify the
	# existence of resource in this way, even though we should be able
	# to provide both supported metadata formats for all records.
	checkPars(pars, [], ["identifier"])
	if pars.has_key("identifier"):
		getServiceRecForIdentifier(pars["identifier"])
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListMetadataFormats[[
			OAI.metadataFormat[
				OAI.metadataPrefix[prefix],
				OAI.schema[schema],
				OAI.metadataNamespace[ns],
			] 
		for prefix, schema, ns in supportedMetadataPrefixes]]
	]


def getListSetsTree(pars):
	"""returns a tree of registrymodel Elements for a ListSets response.
	"""
	checkPars(pars, [])
	return OAI.PMH[
		getResponseHeaders(pars),
		OAI.ListSets[[
			# Once we have better description of sets, add stuff here
			OAI.set[
				OAI.setSpec[set["setName"]],
				OAI.setName[set["setName"]],
			]
		for set in servicelist.getSets()]]
	]


pmhHandlers = {
	"GetRecord": dispatchGetRecordTree,
	"Identify": getIdentifyTree,
	"ListIdentifiers": getListIdentifiersTree,
	"ListMetadataFormats": getListMetadataFormatTree,
	"ListRecords": dispatchListRecordsTree,
	"ListSets": getListSetsTree,
}


def getPMHResponse(args):
	"""returns an ElementTree containing a OAI-PMH response for the query 
	described by pars.
	"""
	pars = {}
	for argName, argVal in args.iteritems():
		if len(argVal)!=1:
			raise BadArgument(argName)
		else:
			pars[argName] = argVal[0]
	try:
		verb = pars["verb"]
	except KeyError:
		raise BadArgument("verb")
	try:
		handler = pmhHandlers[verb]
	except KeyError:
		raise BadVerb("'%s' is an unsupported operation."%pars["verb"])
	return ElementTree.ElementTree(handler(pars).asETree())


def getErrorTree(exception, pars):
	"""returns an ElementTree containing an OAI-PMH error response.

	If exception is one of "our" exceptions, we translate them to error messages.
	Otherwise, we reraise the exception to an enclosing
	function may "handle" it.

	Contrary to the recommendation in the OAI-PMH spec, this will only
	return one error at a time.
	"""
	if isinstance(exception, OAIError):
		code = exception.__class__.__name__
		code = code[0].lower()+code[1:]
		message = str(exception)
	else:
		raise exception
	return ElementTree.ElementTree(OAI.PMH[
		OAI.responseDate[DateTime.now().strftime(_isoTimestampFmt)],
		OAI.request(verb=pars.get("verb", "Identify"), 
				metadataPrefix=pars.get("metadataPrefix")),
		OAI.error(code=code)[
			message
		]
	].asETree())


if __name__=="__main__":
	from gavo import config
	from gavo import nullui
	config.setDbProfile("querulator")
	from gavo.parsing import importparser  # for registration of getRd
	try:
		tree = getPMHResponse({"verb": ["ListRecords"], 
			"metadataPrefix": ["ivo_vor"]})
		for el in tree.getiterator():
			print el, el.attrib
		ElementTree.tostring(tree.getroot())
	except Exception, msg:
		print ">>>>>>>>>>", msg
		getErrorTree(msg, {}).write(sys.stdout)
