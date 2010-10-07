"""
A grammar to parse from primary FITS headers.

This grammar will return exactly one row per source.
"""

import gzip
import re

from gavo import base
from gavo.grammars.common import Grammar, RowIterator, MapKeys
from gavo.utils import fitstools


class FITSProdIterator(RowIterator):
	def _iterRows(self):
		if self.grammar.qnd:
			return self._parseFast()
		else:
			return self._parseSlow()
	
	def _hackBotchedCard(self, card, res):
		"""tries to make *anything* from a card pyfits doesn't want to parse.

		In reality, I'm just trying to cope with oversized keywords.
		"""
		mat = re.match(r"([^\s=]*)\s*=\s*([^/]+)", card._cardimage)
		if mat:
			res[mat.group(1)] = mat.group(2).strip()
		else: # Card beyond recognition, ignore
			pass

	def _buildDictFromHeader(self, header):
		res = {}
		for card in header.ascard:
			try:
				res[card.key.replace("-", "_")] = card.value
			except ValueError:
				self._hackBotchedCard(card, res)
		res["parser_"] = self
		return res
	
	def _parseFast(self):
		fName = self.sourceToken
		if fName.endswith(".gz"):
			f = gzip.open(fName)
		else:
			f = open(fName)
		header = fitstools.readPrimaryHeaderQuick(f)
		f.close()
		row = self._buildDictFromHeader(header)
		yield self.grammar.mapKeys.doMap(row)

	def _parseSlow(self):
		fName = self.sourceToken
		hdus = fitstools.openFits(fName)
		header = hdus[int(self.grammar.hdu)].header
		hdus.close()
		row = self._buildDictFromHeader(header)
		yield self.grammar.mapKeys.doMap(row)
	
	def getLocator(self):
		return self.sourceToken


class FITSProdGrammar(Grammar):
	"""A grammar that returns FITS-headers as dictionaries.

	This is the grammar you want for FITS images, spectra and such.
	"""
	name_ = "fitsProdGrammar"

	_qnd = base.BooleanAttribute("qnd", default=True, description=
		"Use a hack to read the FITS header more quickly.  This only"
		" works for the primary HDU")
	_hduIndex = base.IntAttribute("hdu", default=0,
		description="Take the header from this HDU")
	_mapKeys = base.StructAttribute("mapKeys", childFactory=MapKeys,
		default=None, copyable=True)

	rowIterator = FITSProdIterator

	def onElementComplete(self):
		if self.mapKeys is None:
			self.mapKeys = base.makeStruct(MapKeys)
		self._onElementCompleteNext(FITSProdGrammar)
