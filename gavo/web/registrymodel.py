"""
Data model for the VO registry interface.
"""

from elementtree import ElementTree


OAINamespace = "http://www.openarchives.org/OAI/2.0/"
VOGNamespace = "http://www.ivoa.net/xml/VORegistry/v1.0"
VORNamespace = "http://www.ivoa.net/xml/VOResource/v1.0"

# Since we usually have the crappy namespaced attribute values (yikes!),
# we need this mapping badly.  Don't change it without making sure the
# namespaces aren't referenced in attributes.
ElementTree._namespace_map[VORNamespace] = "vr"
ElementTree._namespace_map[VOGNamespace] = "vg"
ElementTree._namespace_map[OAINamespace] = "oai"

encoding = "utf-8"
XML_HEADER = '<?xml version="1.0" encoding="%s"?>'%encoding


class Element(object):
	"""is an element for serialization into XML.

	This is loosely modelled after nevow stan.

	Don't access the children attribute directly.  I may want to add
	data model checking later, and that would go into addChild.

	When deriving form Elements, you may need attribute names that are not
	python identifiers (e.g., with dashes in them).  In that case, define
	an attribute <att>_name and point it to any string you want as the
	attribute.

	When building an ElementTree out of this, empty elements (i.e. those
	having an empty text and having no non-empty children) are usually
	discarded.  If you need such an element (e.g., for attributes), set
	mayBeEmpty to True.
	"""
	name = None
	namespace = ""
	mayBeEmpty = False

	a_xsi_type = None
	xsi_type_name = "xsi-type"

	def __init__(self, **kwargs):
		self.children = []
		if self.name is None:
			self.name = self.__class__.__name__.split(".")[-1]
		self(**kwargs)

	def __getitem__(self, children):
		if not isinstance(children, (list, tuple)):
			children = [children]
		self.children.extend(children)
		return self

	def __call__(self, **kw):
		if not kw:
			return self

		for k, v in kw.iteritems():
			if k[-1] == '_':
				k = k[:-1]
			elif k[0] == '_':
				k = k[1:]
			attname = "a_"+k
			# Only allow setting attributes already present
			getattr(self, attname)
			setattr(self, attname, v)
		return self

	def __iter__(self):
		raise NotImplementedError, "Element instances are not iterable."

	def isEmpty(self):
		for c in self.children:
			if isinstance(c, basestring):
				if c.strip():
					return False
			elif not c.isEmpty():
				return False
		return True

	def _makeAttrDict(self):
		res = {}
		for name in dir(self):
			if name.startswith("a_") and getattr(self, name)!=None:
				res[getattr(self, name[2:]+"_name", name[2:])] = getattr(self, name)
		return res

	def asETree(self, parent=None):
		"""returns an ElementTree instance for this node.
		"""
		if not self.mayBeEmpty and self.isEmpty():
			return
		elName = ElementTree.QName(self.namespace, self.name)
		attrs = self._makeAttrDict()
		if parent==None:
			node = ElementTree.Element(elName, attrs)
		else:
			node = ElementTree.SubElement(parent, elName, attrs)
		for child in self.children:
			if isinstance(child, basestring):
				node.text = child.encode(encoding)
			else:
				child.asETree(node)
		return node


class OAI:
	"""is a container for classes modelling OAI elements.
	"""
	class OAIElement(Element):
		namespace = OAINamespace

	class PMH(OAIElement):
		name = "OAI-PMH"
	
	class responseDate(OAIElement): pass

	class request(OAIElement):
		a_verb = None

	class Identify(OAIElement): pass
	
	class repositoryName(OAIElement): pass
	
	class baseURL(OAIElement): pass
	
	class adminEmail(OAIElement): pass
	
	class earliestDatestamp(OAIElement): pass
	
	class deletedRecord(OAIElement): pass
	
	class granularity(OAIElement): pass

	class description(OAIElement): pass
	
	class protocolVersion(OAIElement): pass
		


class VOR:
	"""is a container for classes modelling elements from VO Resource.
	"""
	class VORElement(Element):
		namespace = VORNamespace

	class Resource(VORElement):
		a_created = None
		a_updated = None
		a_status = None
	
	class validationLevel(VORElement): pass
	
	class title(VORElement): pass
	
	class shortName(VORElement): pass

	class ResourceName(VORElement):
		a_ivo_id = None

	class identifier(VORElement): pass

	class curation(VORElement): pass
	
	class content(VORElement): pass

	class creator(VORElement): pass
	
	class contributor(VORElement): pass
	
	class date(VORElement):
		a_role = None
	
	class version(VORElement): pass
	
	class contact(VORElement): pass
	
	class publisher(VORElement): pass

	class facility(VORElement): pass

	class instrument(VORElement): pass
	
	class relatedResource(VORElement): pass
	
	class name(VORElement): pass
	
	class address(VORElement): pass
	
	class email(VORElement): pass
	
	class telephone(VORElement): pass
	
	class logo(VORElement): pass
	
	class subject(VORElement): pass
	
	class description(VORElement): pass
	
	class source(VORElement): pass
	
	class referenceURL(VORElement): pass
	
	class type(VORElement): pass
	
	class contentLevel(VORElement): pass
	
	class relationship(VORElement): pass
	
	class rights(VORElement): pass
	
	class capability(VORElement): 
		a_standardID = None
	
	class interface(VORElement):
		a_version = None
		a_role = None

	class accessURL(VORElement):
		a_use = None
	
	class securityMethod(VORElement): pass
	

class VOG:
	"""is a container for classes modelling elements from VO Registry.
	"""
	class VOGElement(Element):
		namespace = VOGNamespace

	class Registry(VOGElement):
		pass
	
	class full(VOGElement):
		pass
	
	class managedAuthority(VOGElement):
		pass
	
	class RegCapRestriction(VOGElement):
		a_standardID = None
	
	class validationLevel(VOGElement):
		pass
	
	class description(VOGElement):
		pass
	
	class interface(VOGElement):
		pass
	
	class Harvest(RegCapRestriction):
		pass
	
	class Search(RegCapRestriction):
		pass

	class maxRecords(VOGElement):
		pass

	class extensionSearchSupport(VOGElement):
		pass
	
	class optionalProtocol(VOGElement):
		pass
	
	class OAIHTTP(VOGElement):
		pass
	
	class OAISOAP(VOGElement):
		pass
	
	class Authority(VOGElement):
		pass
	
	class managingOrg(VOGElement):
		pass

	
import datetime
import time
from gavo import config

def getRegistryURL():
	return (config.get("web", "serverURL")+
		config.get("web", "nevowRoot")+"/registry")

def getRegistryRecord():
	return VOR.Resource(created="2007-08-24", status="active",
		updated="2007-08-24", xsi_type="vg:Registry")[
			VOR.title()["%s publishing registry"%config.get("web",
				"sitename")],
			VOR.identifier()[
				config.get("ivoa", "rootId")+"/DCRegistry"],
			VOR.curation()[
				VOR.publisher()[
					config.getMeta("curation.publisher")],
				VOR.contact()[
					VOR.name()[config.getMeta("curation.contact.name")],
					VOR.email()[config.getMeta("curation.contact.email")],
					VOR.telephone()[config.getMeta("curation.contact.telephone")],
					VOR.address()[config.getMeta("curation.contact.address")],
				],
			],
			VOR.content()[
				VOR.subject()["registry"],
				VOR.description()["%s publishing registry"%config.get("web",
					"sitename")],
				VOR.referenceURL()[getRegistryURL()],
				VOR.type()["Archive"]
			],
			VOR.interface(xsi_type="WebBrowser")[
				VOR.accessURL(use="full")[
					config.get("web", "serverURL")+
					config.get("web", "nevowRoot")+
					"/__system__/services/services/q/form"]
			],
			VOG.managedAuthority()[config.get("ivoa", "managedAuthority")],
		]


def getIdentifyTree():
	return OAI.PMH()[
		OAI.responseDate()[datetime.datetime.utcfromtimestamp(
			time.time()).isoformat()],
		OAI.request()(verb="Identify")[getRegistryURL()],
		OAI.Identify()[
			OAI.repositoryName()["%s publishing registry"%config.get("web",
				"serverURL")],
			OAI.baseURL()[getRegistryURL()],
			OAI.protocolVersion()["2.0"],
			OAI.adminEmail()[config.get("operator")],
			OAI.earliestDatestamp()["1970-01-01"],
			OAI.deletedRecord()["no"],
			OAI.granularity()["YYYY-MM-DDThh:mm:ssZ"],
		],
		OAI.description()[
			getRegistryRecord(),
		],
	]

print ElementTree.tostring(getIdentifyTree().asETree())
