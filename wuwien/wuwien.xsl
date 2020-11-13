<?xml version="1.0"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

<xsl:output method="xml" encoding="UTF-8" indent="yes"/>

<xsl:param name="year"/>

<xsl:template match="/">

<xsl:processing-instruction name="xml-stylesheet">
  <xsl:text>type="text/css" href="https://cdn.jsdelivr.net/npm/om-style@1.0.0/basic.css"</xsl:text>
</xsl:processing-instruction>

<xsl:processing-instruction name="xml-stylesheet">
  <xsl:text>type="text/css" href="https://cdn.jsdelivr.net/npm/om-style@1.0.0/lightgreen.css"</xsl:text>
</xsl:processing-instruction>

<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd">

<canteen>
    <xsl:for-each select="RESPONSE/TAGESPLAN">
        <day>
            <xsl:attribute name="date"><xsl:value-of select="$year" />-<xsl:choose>
                <xsl:when test="contains(@datum, 'Januar')">01</xsl:when>
                <xsl:when test="contains(@datum, 'Februar')">02</xsl:when>
                <xsl:when test="contains(@datum, 'März')">03</xsl:when>
                <xsl:when test="contains(@datum, 'April')">04</xsl:when>
                <xsl:when test="contains(@datum, 'Mai')">05</xsl:when>
                <xsl:when test="contains(@datum, 'Juni')">06</xsl:when>
                <xsl:when test="contains(@datum, 'Juli')">07</xsl:when>
                <xsl:when test="contains(@datum, 'August')">08</xsl:when>
                <xsl:when test="contains(@datum, 'September')">09</xsl:when>
                <xsl:when test="contains(@datum, 'Oktober')">10</xsl:when>
                <xsl:when test="contains(@datum, 'October')">10</xsl:when>
                <xsl:when test="contains(@datum, 'November')">11</xsl:when>
                <xsl:when test="contains(@datum, 'Dezember')">12</xsl:when>
              </xsl:choose>-<xsl:value-of select="substring-before(@datum, '.')" /></xsl:attribute>
        <xsl:choose>
          <xsl:when test="ITEM//SPEISE//KOMPONENTE//NAME">
            <xsl:for-each select="ITEM">
              <xsl:if test="SPEISE//KOMPONENTE//NAME">
                <category>
                    <xsl:attribute name="name">
                      <xsl:value-of select="NAME" />
                      <xsl:text> (</xsl:text>
                      <xsl:value-of select="AUSGABE" />
                      <xsl:text>)</xsl:text>
                    </xsl:attribute>
                    <xsl:for-each select="SPEISE">
                      <xsl:variable name="price">
                          <xsl:value-of select="substring-before(substring-after(PREIS,' '), ',')" />
                          <xsl:text>.</xsl:text>
                          <xsl:value-of select="substring-after(PREIS, ',')" />
                      </xsl:variable>
                      <xsl:if test="KOMPONENTE//NAME">
                        <meal>
                            <name>
                              <xsl:for-each select="KOMPONENTE">
                                <xsl:value-of select="NAME"/>
                                <xsl:if test="position() != last()">
                                  <xsl:text> </xsl:text>
                                </xsl:if>
                              </xsl:for-each>
                            </name>
                            <xsl:for-each select="KOMPONENTE">
                              <xsl:if test="string-length(ZUTATEN) &gt; 0">
                                <note>
                                  <xsl:value-of select="ZUTATEN"/>
                                </note>
                              </xsl:if>
                            </xsl:for-each>
                            <xsl:if test="number($price) &gt; 0.0">
                              <price role="student">
                                <xsl:value-of select="$price"/>
                              </price>
                            </xsl:if>
                        </meal>
                      </xsl:if>
                    </xsl:for-each>
                </category>
              </xsl:if>
            </xsl:for-each>
          </xsl:when>
          <xsl:otherwise>
            <closed />
          </xsl:otherwise>
        </xsl:choose>
        </day>
    </xsl:for-each>
</canteen>
</openmensa>
</xsl:template>
</xsl:stylesheet>
