"""
Binary VOTable encoding.
"""

import struct
import traceback

from gavo.votable import coding
from gavo.votable import common


floatNaN = struct.pack("!f", common.NaN)
doubleNaN = struct.pack("!d", common.NaN)


def _getArrayShapingCode(field, padder):
	"""returns common code for almost all array serialization.

	Field must describe an array (as opposed to a single value).

	padder must be python-source for whatever is used to pad
	arrays that are too short.
	"""
	base = [
		"if val is None: val = []"]
	if field.a_arraysize=='*':
		return base+["tokens.append(struct.pack('!i', len(val)))"]
	else:
		return base+["val = coding.trim(val, %s, %s)"%(
			repr(field.a_arraysize), padder)]


def _addNullvalueCode(field, nullvalue, src):
	"""adds code to let null values kick in a necessary.
 
	nullvalue here has to be a ready-made *python* literal.  Take care
	when passing in user supplied values here.
	"""
	if nullvalue is None:
		action = ("  raise common.BadVOTableData('None passed for field"
			" that has no NULL value', None, '%s')")%field.getDesignation()
	else:
		action = "  tokens.append(%s)"%nullvalue
	return [
		"if val is None:",
		action,
		"else:"
		]+coding.indentList(src, "  ")


def _makeBooleanEncoder(field):
	return [
		"if val is None:",
		"  tokens.append('?')",
		"elif val:",
		"  tokens.append('1')",
		"else:",
		"  tokens.append('0')",
	]


def _makeBitEncoder(field, arraysize=None):
	# bits and bit arrays are just (possibly long) integers
	# arraysize is only passed for actual arrays.
	src = [
		"if val is None:",
		"  raise common.BadVOTableData('Bits have no NULL value', None,",
		"    '%s')"%field.getDesignation(),
		"tmp = []",
		"curByte, rest = val%256, val//256",
		"while curByte:",
		"  tmp.append(chr(curByte))",
		"  curByte, rest = rest%256, rest//256",
		"if not tmp:",   # make sure we leave somthing even for 0
		"  tmp.append(chr(0))",
		"tmp.reverse()",]

	if arraysize:  # this not just a single bit
		if arraysize=="*":  # variable length: dump number of bits
			src.extend([
				"tokens.append(struct.pack('!i', len(tmp)*8))"])
		else:  # crop/expand as necesary
			numBytes = int(arraysize)//8+(not not int(arraysize)%8)
			src.extend([
				"if len(tmp)<%d: tmp = [chr(0)]*(%d-len(tmp))+tmp"%(
					numBytes, numBytes),
				"if len(tmp)>%d: tmp = tmp[-%d:]"%(numBytes, numBytes)])
	
	src.extend([
		"tokens.append(struct.pack('%ds'%len(tmp), ''.join(tmp)))"])
	return src


def _generateFloatEncoderMaker(fmtCode, nullName):
	def makeFloatEncoder(field):
		return [
			"if val is None:",
			"  tokens.append(%s)"%nullName,
			"else:",
			"  tokens.append(struct.pack('%s', val))"%fmtCode]
	return makeFloatEncoder


def _generateComplexEncoderMaker(fmtCode, singleNull):
	def makeComplexEncoder(field):
		return [
			"if val is None:",
			"  tokens.append(%s+%s)"%(singleNull, singleNull),
			"else:",
			"  tokens.append(struct.pack('%s', val.real, val.imag))"%fmtCode]
	return makeComplexEncoder


def _generateIntEncoderMaker(fmtCode):
	def makeIntEncoder(field):
		nullvalue = coding.getNullvalue(field, int)
		if nullvalue is not None:
			nullvalue = repr(struct.pack(fmtCode, int(nullvalue)))
		return _addNullvalueCode(field, nullvalue,[
			"tokens.append(struct.pack('%s', val))"%fmtCode])
	return makeIntEncoder


def _makeCharEncoder(field):
	nullvalue = coding.getNullvalue(field, lambda _: True)
	if nullvalue is not None:
		nullvalue = repr(struct.pack("c", nullvalue))
	return _addNullvalueCode(field, nullvalue, [
		"tokens.append(struct.pack('c', val))"])


def _makeUnicodeCharEncoder(field):
	nullvalue = coding.getNullvalue(field, lambda _: True)
	if nullvalue is not None:
		coded = nullvalue.encode("utf-16be")
		nullvalue = repr(struct.pack("%ds"%len(coded), coded))
	return _addNullvalueCode(field, nullvalue, [
		"coded = val.encode('utf-16be')",
		"tokens.append(struct.pack('%ds'%len(coded), coded))"])


_encoders = {
		"boolean": _makeBooleanEncoder,
		"bit": _makeBitEncoder,
		"unsignedByte": _generateIntEncoderMaker('B'),
		"short": _generateIntEncoderMaker('!h'),
		"int": _generateIntEncoderMaker('!i'),
		"long": _generateIntEncoderMaker('!q'),
		"char": _makeCharEncoder,
		"unicodeChar": _makeUnicodeCharEncoder,
		"double": _generateFloatEncoderMaker("!d", "doubleNaN"),
		"float": _generateFloatEncoderMaker("!f", "floatNaN"),
		"doubleComplex": _generateComplexEncoderMaker("!dd", "doubleNaN"),
		"floatComplex": _generateComplexEncoderMaker("!ff", "floatNaN"),
}

def _getArrayEncoderLines(field):
	"""returns python lines to encode array values of field.
	"""
	type, arraysize = field.a_datatype, field.a_arraysize
	# bit array literals are integers, same as bits
	if type=="bit":
		return _makeBitEncoder(field, arraysize)

	# Everything else can use some common array shaping code since value comes in
	# some kind of sequence.
	if type=="char":
		# strings
		padder = "' '"
		src = ["tokens.append(struct.pack('%ds'%len(val), val))"]

	elif type=="unicodeChar":
		padder = "' '"
		src = [
			"coded = val.encode('utf-16be')",
			"tokens.append(struct.pack('%ds'%len(coded), coded))"]

	else:  # everything else is just concatenating individual coded strings
		padder = '[None]'
		src = [ # Painful name juggling to avoid having to call functions.
			"fullTokens = tokens",
			"tokens = []",
			"if val is None:",
			"  arr = []",
			"else:",
			"  arr = val",
			"for val in arr:"
		]+coding.indentList(_encoders[field.a_datatype](field), "  ")

		src.extend([
			"fullTokens.append(''.join(tokens))",
			"tokens = fullTokens"])
			
	return _getArrayShapingCode(field, padder)+src
			
			

def getLinesFor(field):
	"""returns a sequence of python source lines to encode values described
	by field into tabledata.
	"""
	if field.a_arraysize in common.SINGLEVALUES:
		return _encoders[field.a_datatype](field)
	else:
		return _getArrayEncoderLines(field)


def getPostamble(tableDefinition):
	return [
		"return ''.join(tokens)"]


def getGlobals():
	return globals()