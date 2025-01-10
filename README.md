# XML Schema Definition Converter

`xsdc` (XSD Converter or XML Schema Definition Converter) is a command line tool for converting XML Schema Definition (XSD) to JSON Schema.

## Quickstart

Install uv and xsdc.

```sh
pip install -U uv
uv sync
xsdc --help
```

## Example

```sh
xsdc convert -f ./examples/XMLSchema.xsd
```

## Python Code Generation

You can also use `datamodel-codegen` to generate pydantic models from the JSON Schema.

```shgit add
datamodel-codegen --input .\xsd-jsonschema.json --input-file-type jsonschema --output models.py
```

## Disclaimer

Please note that this tool is provided as-is and may not cover all edge cases. While it aims to handle most straightforward scenarios effectively, users should exercise caution and validate the output for their specific use cases.
