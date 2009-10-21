from gavo.adql.annotations import annotate
from gavo.adql.common import *
from gavo.adql.tree import (
	getTreeBuildingGrammar, registerNode)
from gavo.adql.nodes import (flatten, registerRegionMaker)
from gavo.adql.grammar import (
	getADQLGrammar as getRawGrammar, 
	ParseException)
from gavo.adql.morphpg import (
	morphPG,
	insertQ3Calls)

def getSymbols():
	return getTreeBuildingGrammar()[0]

def getGrammar():
	return getTreeBuildingGrammar()[1]

def parseToTree(adqlStatement):
	return getGrammar().parseString(adqlStatement)[0]
