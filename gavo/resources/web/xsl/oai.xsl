<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:oai="http://www.openarchives.org/OAI/2.0/"
    xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
   
    <!-- ################################################# Configuration

    The idea is to define named templates that are inserted at certain
    places in all top-level templates.  This is mainly to allow custom
    head elements (stylesheet...) or foot lines. -->

    <xsl:template name="localCompleteHead">
        <link rel="stylesheet" href="/static/css/gavo_dc.css"
            type="text/css"/>
        <!-- in GAVO DC, don't index this, there are better meta pages -->
        <meta name="robots" content="noindex,nofollow"/>
    </xsl:template>

    <xsl:template name="localMakeFoot">
        <hr/>
        <a href="/">The GAVO Data Center</a>
    </xsl:template>


    <!-- ############################################## Global behaviour -->

    <xsl:output method="xml" 
      doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
      doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

    <!-- Don't spill the content of unknown elements. -->
    <xsl:template match="text()"/>

	  <xsl:template match="oai:OAI-PMH">
        <html>
            <head>
                <title>OAI PMH</title>
                <xsl:call-template name="localCompleteHead"/>
                <style type="text/css"><![CDATA[
                    .nestbox {
                        padding: 1ex;
                        margin-top: 2ex;
                        border: 1px solid grey;
                        position: relative;
                    }
                    .boxtitle {
                        background-color: white;
                        position: absolute;
                        top: -3ex;
                    }
                ]]></style>
            </head>
            <body>
                <h1>OAI PMH result of <xsl:value-of select="oai:responseDate"/>
                </h1>
    				    <xsl:apply-templates/>
    				    <p><a href="/oai.xml?verb=ListIdentifiers&amp;metadataPrefix=ivo_vor">All identifiers defined here</a></p>
                <xsl:call-template name="localMakeFoot"/>
            </body>
        </html>
    </xsl:template>

    <xsl:template match="oai:request">
        <p class="reqinfo">
            Request verb was <xsl:value-of select="@verb"/>
        </p>
    </xsl:template>

    <xsl:template match="oai:error">
        <div class="errors"><p>Error code <xsl:value-of select="@code"/>:
            <xsl:value-of select="."/></p>
        </div>
    </xsl:template>

    <xsl:template match="oai:ListIdentifiers">
        <ul class="listIdentifiers">
            <xsl:apply-templates/>
        </ul>
    </xsl:template>

    <xsl:template match="oai:header">
        <li class="oairec">
            <xsl:apply-templates/>
        </li>
    </xsl:template>

    <xsl:template match="oai:identifier">
        <xsl:element name="a">
            <xsl:attribute name="href">/oai.xml?verb=GetRecord&amp;metadataPrefix=ivo_vor&amp;identifier=<xsl:value-of select="."/>
            </xsl:attribute>
            <xsl:value-of select="."/>
        </xsl:element>
    </xsl:template>

    <xsl:template match="oai:metadata">
        <xsl:apply-templates mode="dumpall"/>
    </xsl:template>

    <xsl:template match="*" mode="dumpall">
        <div class="nestbox">
            <p class="boxtitle"><xsl:value-of select="name(.)"/></p>
            <xsl:apply-templates mode="dumpall"/>
        </div>
    </xsl:template>
</xsl:stylesheet>


<!-- vim:et:sw=4:sta
-->