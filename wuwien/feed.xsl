<?xml version="1.0"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">

<xsl:output method="xml" encoding="UTF-8" indent="yes"/>

<xsl:template match="/">

<xsl:processing-instruction name="xml-stylesheet">
  <xsl:text>type="text/css" href="https://cdn.jsdelivr.net/npm/om-style@1.0.0/basic.css"</xsl:text>
</xsl:processing-instruction>

<xsl:processing-instruction name="xml-stylesheet">
  <xsl:text>type="text/css" href="https://cdn.jsdelivr.net/npm/om-style@1.0.0/lightgreen.css"</xsl:text>
</xsl:processing-instruction>

<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd">

<canteen>
    <xsl:for-each select="NewDataSet//WeekDay">
        <day>
            <xsl:attribute name="date">
              <xsl:value-of select="@Date" />
          </xsl:attribute>
        <xsl:choose>
          <xsl:when test="MenuLine//SetMenu//Component//ComponentDetails//GastDesc//@value">
            <xsl:for-each select="MenuLine">
              <xsl:if test="SetMenu//Component//ComponentDetails//GastDesc//@value">
                <category>
                    <xsl:attribute name="name">
                      <xsl:value-of select="@Name" />
                    </xsl:attribute>
                    <xsl:for-each select="SetMenu//Component">
                      <xsl:if test="ComponentDetails//GastDesc//@value">
                        <meal>
                            <name>
                              <xsl:value-of select="ComponentDetails//GastDesc//@value" />
                            </name>
                            <xsl:for-each select="AdditiveInfo//AdditiveGroup//Additive">
                              <xsl:if test="string-length(@name) &gt; 0">
                                <note>
                                  <xsl:value-of select="@name"/>
                                </note>
                              </xsl:if>
                            </xsl:for-each>
                            <xsl:for-each select="ancestor::SetMenu[1]//SetMenuDetails//AdditiveInfo//AdditiveGroup//Additive">
                              <xsl:if test="string-length(@name) &gt; 0">
                                <note>
                                  <xsl:value-of select="@name"/>
                                </note>
                              </xsl:if>
                            </xsl:for-each>
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
