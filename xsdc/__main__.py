import logging
import os

import click
from lxml import etree

from xsdc import logger, settings
from xsdc.strip_comments import strip_comments
from xsdc.xsdtojson import convert_xsd_to_jsonschema


@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.group()
def cli(debug: bool = settings.debug):
    """
    CLI tool for XSD Converter (xsdc).

    xsdc provides various commands and options to interact with XSD (XML Schema Definition) files.
    """
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")


@cli.command()
@click.option(
    "--filepath",
    "-f",
    required=True,
    help="Path to the XML or XSD file or directory",
)
def strip(filepath: str):
    """
    Command to strip comments from XML or XSD files.

    This command takes a path to an XML or XSD file or a directory containing such files,
    and removes all comments from the files.

    Example:
        strip --path /path/to/file_or_directory
    """
    strip_comments(filepath)


@cli.command()
@click.option("--xml-file", required=True, help="Path to the XML file")
@click.option("--xsl-file", required=True, help="Path to the XSL file")
@click.option("--out", "-o", required=False, help="Path to the output file")
def transform(xml_file: str, xsl_file: str, out: str | None):
    """
    Transforms an XML file using an XSLT file.

    Example:
        xsdc --xml-file example.xml --xsl-file transform.xsl --out result.xml
    """
    dom = etree.parse(xml_file)
    xslt = etree.parse(xsl_file)
    transform = etree.XSLT(xslt)
    newdom = transform(dom)
    if out is None:
        print(newdom)
    else:
        with open(out, "wb") as f:
            f.write(newdom)


@cli.command()
@click.option("--xsd-file", "-f", required=True, help="Path to the XSD file")
@click.option("--out", "-o", required=False, help="Path to the output file")
@click.option("--anonymous-groups", "-g", is_flag=True, help="Allow anonymous groups")
def convert(xsd_file: str, out: str | None, anonymous_groups: bool = False):
    """
    Converts an XSD file to a JSON Schema file.

    Example:
        xsdc convert -f example.xsd
    """
    if out is None:
        base, ext = os.path.splitext(os.path.basename(xsd_file))
        if ext:
            out = os.path.join(os.getcwd(), base + "-jsonschema.json")
        else:
            out = os.path.join(os.getcwd(), xsd_file + "-jsonschema.json")

    convert_xsd_to_jsonschema(xsd_file, out, not anonymous_groups)


if __name__ == "__main__":
    cli()
