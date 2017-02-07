"""
Generating geojson files.

This requires annotation with the geojson (DaCHS-private) data model.

See separate documentation in the reference documentation.

No streaming is forseen for this format for now; whatever a web browser
can cope with, we can, too.  I hope.

To add more geometry types, pick a type name (typically different
from what geojson calls the thing because it also depends on the input),
add it to _FEATURE_MAKERS and write the Factory, taking _getSepcooFactory as
a model.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import json

from gavo import base
from gavo.formats import common


def _makeCRS(gjAnnotation):
	"""returns a dictionary to add a geoJSON CRS structure from a DaCHS
	annotation to a dictionary.
	"""
	try:
		rawCRS = gjAnnotation["crs"]
		if rawCRS["type"]=="name":
			return {"crs": {
					"type": "name",
					"properties": {
						"name": rawCRS["properties"]["name"],
					}
				}
			}

		elif rawCRS["type"]=="link":
			return {"crs": {
					"type": "url",
					"properties": {
						"href": rawCRS["properties"]["href"],
						"type": rawCRS["properties"]["type"],
					}
				}
			}

		else:
			raise base.DataError("Unknown GeoJSON CRS type: %s"%rawCRS["type"])

	except KeyError:
		return {}


def _makeFeatureFactory(tableDef, skippedFields, geoFactory):
	"""returns a factory function for building geoJson features from
	rowdicts.

	skippedFields are not included in the properties (i.e., they're
	what geometry is built from),, geoFactory is a function returning
	the geometry itself, given a row.
	"""
	propertiesFields = [f.name for f in tableDef.columns 
		if f.name not in skippedFields]

	def buildFeature(row):
		feature = geoFactory(row)
		feature["properties"] = dict((n, row[n]) for n in propertiesFields)
		return feature
	
	return buildFeature


def _getSepsimplexFactory(tableDef, geometryAnnotation):
	"""returns a row factory for polygons specified with a min/max coordinate
	range.

	This expects c1min/max, c2min/max keys.
	"""
	c1min = geometryAnnotation["c1min"].value.name
	c1max = geometryAnnotation["c1max"].value.name
	c2min = geometryAnnotation["c2min"].value.name
	c2max = geometryAnnotation["c2max"].value.name

	return _makeFeatureFactory(tableDef, 
		[c1min, c2min, c1max, c2max],
		lambda row: {
			"type": "Polygon",
			"coordinates": [
				[row[c1min], row[c2min]],
				[row[c1min], row[c2max]],
				[row[c1max], row[c2max]],
				[row[c1max], row[c2min]],
				[row[c1min], row[c2min]]]})


def _getSeppolyFactory(tableDef, geometryAnnotation):
	"""returns a features factory for polygons made of separate 
	coordinates.

	This expects cn_m keys; it will gooble them up until the first is not
	found.  m is either 1 or 2.
	"""
	# hard code the assumption that these are column annotations for now
	# -- make a type check if we may put in literals
	cooIndex = 1
	polyCoos, ignoredNames = [], set()
	while True:
		try:
			polyCoos.append((
				geometryAnnotation["c%d_1"%cooIndex].value.name,
				geometryAnnotation["c%d_2"%cooIndex].value.name))
			ignoredNames |= set(polyCoos[-1])
		except KeyError:
			break
		cooIndex += 1
	polyCoos.append(polyCoos[0])

	return _makeFeatureFactory(tableDef, 
		ignoredNames,
		lambda row: {
			"type": "Polygon",
			"coordinates": [[row[name1], row[name2]] 
				for name1, name2 in polyCoos]})


def _getSepcooFactory(tableDef, geometryAnnotation):
	"""returns a features factory for points made up of separate coordinates.

	This expects latitude and longitude keys.
	"""
	# hard code the assumption that these are column annotations for now
	# -- make a type check if we may put in literals
	latCoo = geometryAnnotation["latitude"].value.name
	longCoo = geometryAnnotation["longitude"].value.name
	return _makeFeatureFactory(tableDef, 
		[latCoo, longCoo],
		lambda row: {
			"type": "Point",
			"coordinates": [row[longCoo], row[latCoo]]})


# a dict mapping feature.geometry.type names to row factories dealing
# with them
_FEATURE_MAKERS = {
	"sepcoo": _getSepcooFactory,
	"seppoly": _getSeppolyFactory,
	"sepsimplex": _getSepsimplexFactory,
}

def _makeFeatures(table, gjAnnotation):
	"""returns a list of geoJSON features from the (annotated) table.
	"""
	geometryAnnotation = gjAnnotation["feature"]["geometry"]
	try:
		makeFeature = _FEATURE_MAKERS[
			geometryAnnotation["type"]](
				table.tableDef, geometryAnnotation)
	except KeyError, msg:
		raise base.ui.logOldExc(
			base.DataError("Invalid geoJSON annotation on table %s: %s missing"%(
				table.tableDef.id, msg)))
	
	return [
		makeFeature(r) for r in table]


def writeTableAsGeoJSON(table, target, acquireSamples=False):
	"""writes a table as geojson.

	This requires an annotation with geojson:FeatureCollection.
	"""
	for ann in table.tableDef.annotations:
		if ann.type=="geojson:FeatureCollection":
			break
	else:
		raise base.DataError("Table has no geojson:FeatureCollection annotation."
			"  Cannot serialise to GeoJSON.")

	result = {
		"type": "FeatureCollection",
		"features": _makeFeatures(table, ann),
	}
	result.update(_makeCRS(ann))

	return json.dump(result, target, encoding="utf-8")


# NOTE: while json could easily serialize full data elements,
# right now we're only writing single tables.
common.registerDataWriter("geojson", 
	writeTableAsGeoJSON, "application/geo+json", "GeoJSON")
