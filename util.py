#!/usr/bin/env python

import re
import datetime
from zoneinfo import ZoneInfo
import lxml
import lxml.etree
from pyopenmensa.feed import LazyBuilder


__all__ = ['xml_escape', 'xml_remove_invalid_chars', 'StyledLazyBuilder',
           'now_local', 'xml_str_param', 'meta_from_xsl', 'weekdays_map',
           'parse_opening_times']

default_style_sheets = ('https://cdn.jsdelivr.net/npm/om-style@1.0.0/basic.css',
                        'https://cdn.jsdelivr.net/npm/om-style@1.0.0/lightgreen.css')


def xml_escape(s, escape_double_quotes=False):
    s = str(s).replace('&', '&amp;')  # amp first!
    s = s.replace('>', '&gt;')
    s = s.replace('<', '&lt;')
    if escape_double_quotes:
        s = s.replace('"', '&quot;')
    return s


def xml_remove_invalid_chars(s):
    # https://www.w3.org/TR/xml/#char32
    restricted_chars = re.compile(
        r'[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\u10000-\u10FFFF]')
    return restricted_chars.sub('', s)


class StyledLazyBuilder(LazyBuilder):
    def toXMLFeed(self, styles=default_style_sheets):
        feed = self.toXML()
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        if styles:
            for style in styles:
                xml_header += '<?xml-stylesheet href="' + \
                    xml_escape(style, True) + '" type="text/css"?>\n'
        return xml_remove_invalid_chars(xml_header + feed.toprettyxml(indent='  '))


def now_local():
    berlin = ZoneInfo('Europe/Berlin')
    now = datetime.datetime.now(tz=berlin)
    return now


def xml_str_param(s):
    return lxml.etree.XSLT.strparam(str(s))


def parse_opening_times(times):
    r"""
    Read opening hours such as "Mo-Do 11:00-14:00 Uhr\nFr 11:00-13:30 Uhr".

    Returns a dict from the English two-letter weekday ("Mo", "Tu", ...) to
    "HH:MM-HH:MM". German abbreviations (Di, Mi, Do, So) are accepted as
    well: most canteen lists in this repository are written in German, and
    "Do" or "So" used to be skipped, so a range like "Mo-Do" never ended and
    ran on through Saturday and Sunday.
    """
    opening_times = {}
    pattern = re.compile(
        r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*"
        r"(\d{1,2})[:\.](\d{2})\s*[-–]\s*(\d{1,2})[:\.](\d{2})(?:\s*Uhr)?",
        flags=re.IGNORECASE)
    weekdays = [short for short, _ in weekdays_map]

    for result in re.findall(pattern, times):
        from_day, _, to_day, from_time_hours, from_time_minutes, to_time_hours, to_time_minutes = result
        value = "%02d:%02d-%02d:%02d" % (
            int(from_time_hours), int(from_time_minutes), int(to_time_hours), int(to_time_minutes))
        first = weekday_short(from_day)
        if first not in weekdays:
            continue
        if not to_day:
            opening_times[first] = value
            continue
        last = weekday_short(to_day)
        if last not in weekdays:
            continue
        for short in weekdays[weekdays.index(first):weekdays.index(last) + 1]:
            opening_times[short] = value

    return opening_times


def weekday_short(day):
    """Map a German or English two-letter weekday to the English one."""
    day = day[:1].upper() + day[1:].lower()
    return german_weekdays.get(day, day)


def meta_from_xsl(file_name, data):
    """Generate an openmensa XML meta feed using XSLT"""

    if "times" in data:
        opening_times = parse_opening_times(data["times"])
        for short, long in weekdays_map:
            if short in opening_times:
                data[long] = xml_str_param(opening_times[short])
        data["times"] = xml_str_param(True)

    # Generate xml
    xslt_tree = lxml.etree.parse(file_name)
    xslt = lxml.etree.XSLT(xslt_tree)
    return lxml.etree.tostring(xslt(lxml.etree.Element("foobar"), **data),
                               pretty_print=True,
                               xml_declaration=True,
                               encoding="utf-8").decode("utf-8")


weekdays_map = [
    ("Mo", "monday"),
    ("Tu", "tuesday"),
    ("We", "wednesday"),
    ("Th", "thursday"),
    ("Fr", "friday"),
    ("Sa", "saturday"),
    ("Su", "sunday")
]

german_weekdays = {"Di": "Tu", "Mi": "We", "Do": "Th", "So": "Su"}
