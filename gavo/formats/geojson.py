"""
Generating geojson (RFC 7946) files.

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
from gavo.utils import serializers


# we need to protect some of our columns from being mapped (by giving
# them a magic attribute), hence a special MFRegistry

JSON_MF_REGISTRY = serializers.defaultMFRegistry.clone()
registerMF = JSON_MF_REGISTRY.registerFactory

def _rawMapperFactory(colDesc):
	if hasattr(colDesc.original, "geojson_do_not_touch"):
		return lambda val: val
registerMF(_rawMapperFactory)


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


def _getGeometryFactory(tableDef, geometryAnnotation):
	"""returns a row factory for a geometry-valued column.

	This expects a value key referencing a column typed either
	spoint or spoly.
	"""
	geoCol = geometryAnnotation["value"].value

	if geoCol.type=="spoint":
		def annMaker(row):
			return {
				"type": "Point",
				"coordinates": list(row[geoCol.name].asCooPair())}
		geoCol.geojson_do_not_touch = True
	
	elif geoCol.type=="spoly":
		def annMaker(row):
			return {
				"type": "Polygon",
				"coordinates": [list(p) for p in
					row[geoCol.name].asCooPairs()]}
		geoCol.geojson_do_not_touch = True
	
	else:
		raise base.DataError("Cannot serialise %s-valued columns"
			" with a 'geometry' geometry type (only spoint and spoly)")
	
	return _makeFeatureFactory(tableDef, [geoCol.name], annMaker)


def _getSepsimplexFactory(tableDef, geometryAnnotation):
	"""returns a row factory for polygons specified with a min/max coordinate
	range.

	This expects c1min/max, c2min/max keys.  It does not do anything special
	if the simplex spans the stitching line.
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
	"geometry": _getGeometryFactory,
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

	sm = base.SerManager(table, acquireSamples=False,
		mfRegistry=JSON_MF_REGISTRY)

	# let geo builders manually ignore rows they can't do anything with
	features = []
	for r in sm.getMappedValues():
		try:
			features.append(makeFeature(r))
		except base.SkipThis:
			pass
	return features

def writeTableAsGeoJSON(table, target, acquireSamples=False):
	"""writes a table as geojson.

	This requires an annotation with geojson:FeatureCollection.
	"""
	# for now, don't bother with complete data items, just serialise the
	# primary table.
	if hasattr(table, "getPrimaryTable"):
		table = table.getPrimaryTable()

	try:
		ann = table.tableDef.getAnnotationOfType("geojson:FeatureCollection")
	except base.NotFoundError:
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
