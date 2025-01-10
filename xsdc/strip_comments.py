#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["lxml"]
# ///
import os
import sys

from lxml import etree

XSLT_STRIP_COMMENTS = """<?xml version="1.0"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:xd="http://www.oxygenxml.com/ns/doc/xsl"
    exclude-result-prefixes="xs xd"
    version="2.0">
    <xsl:output method="xml" indent="yes"/> 
    <xsl:strip-space elements="*"/>
    <xsl:template match="@*|node()">
        <xsl:copy>
            <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
    </xsl:template>
    <xsl:template match="comment()|xs:annotation" priority="5"/>
</xsl:stylesheet>
"""


def apply_xsl(file_path):
    dom = etree.parse(file_path)
    xslt_root = etree.XML(XSLT_STRIP_COMMENTS)
    transform = etree.XSLT(xslt_root)
    new_dom = transform(dom)
    new_dom.write(file_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    print(f"Processed file: {file_path}")


def process_directory(directory):
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".xml") or file.endswith(".xsd"):
                file_path = os.path.join(root, file)
                apply_xsl(file_path)


def strip_comments(file_or_directory):
    if os.path.isfile(file_or_directory):
        apply_xsl(file_or_directory)
    elif os.path.isdir(file_or_directory):
        process_directory(file_or_directory)
    else:
        raise ValueError(f"Error: {file_or_directory} is not a valid file or directory")


def main():
    if len(sys.argv) != 2:
        print("Usage: strip_comments.py <file_or_directory>")
        sys.exit(1)

    input_path = sys.argv[1]

    if os.path.isfile(input_path):
        apply_xsl(input_path)
    elif os.path.isdir(input_path):
        process_directory(input_path)
    else:
        print(f"Error: {input_path} is not a valid file or directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
