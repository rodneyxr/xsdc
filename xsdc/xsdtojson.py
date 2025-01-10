import json
import os
import re

import xmlschema
from xmlschema import XsdAttribute, XsdElement, XsdType
from xmlschema.validators import (
    XsdAnyAttribute,
    XsdAnyElement,
    XsdComplexType,
    XsdGroup,
    XsdUnion,
)

from xsdc import logger

##############################################################################
# Mapping from XSD built-in types to JSON Schema types
##############################################################################
BUILTIN_MAP = {
    "string": "string",
    "normalizedString": "string",
    "token": "string",
    "language": "string",
    "boolean": "boolean",
    "decimal": "number",
    "integer": "integer",
    "long": "integer",
    "int": "integer",
    "short": "integer",
    "byte": "integer",
    "unsignedByte": "integer",
    "unsignedShort": "integer",
    "unsignedInt": "integer",
    "unsignedLong": "integer",
    "positiveInteger": "integer",
    "negativeInteger": "integer",
    "nonNegativeInteger": "integer",
    "nonPositiveInteger": "integer",
    "float": "number",
    "double": "number",
    "dateTime": "string",
    "date": "string",
    "time": "string",
    "duration": "string",
    "anyURI": "string",
    "base64Binary": "string",
    "hexBinary": "string",
    "QName": "string",
    "NOTATION": "string",
}


def map_xsd_builtin_to_json_type(xsd_builtin_name):
    """
    Convert an XSD built-in type (e.g., 'string', 'boolean') into
    the best JSON Schema 'type' we can.
    """
    return BUILTIN_MAP.get(xsd_builtin_name, "string")


##############################################################################
# Helper / utility functions
##############################################################################


def normalize_name(o: XsdType):
    """
    Normalize the name of an XSD type object.

    Parameters:
    o (XsdType): The XSD type object to normalize.

    Returns:
    str: The normalized name. If the object's name is not set, returns an empty string.
         If the display name starts with '{', returns the local name. Otherwise, returns the display name.
    """
    if not o.name:
        return ""
    if o.display_name.startswith("{"):
        return o.local_name
    return o.display_name


def make_array_schema(item_schema, min_occurs, max_occurs):
    """
    Turn a property into an "array" schema if maxOccurs > 1 or is unbounded.
    """
    array_schema = {"type": "array", "items": item_schema}
    if min_occurs is not None and min_occurs > 0:
        array_schema["minItems"] = min_occurs
    else:
        array_schema["minItems"] = 0  # default

    if max_occurs is not None:
        array_schema["maxItems"] = max_occurs

    return array_schema


##############################################################################
# Core conversion functions
##############################################################################


def convert_xsd_type(
    xsd_type: XsdType, definitions, visited=None, flatten_anonymous=False
):
    """
    Main dispatcher to handle either a simple or complex type from xmlschema.
    We'll store results in 'definitions' if this is a named type.

    :param xsd_type: An instance of xmlschema.XsdType (simple or complex).
    :param definitions: dict to store named schema definitions.
    :param visited: set of qnames we have already visited, to avoid recursion loops.
    :param flatten_anonymous: bool to indicate if anonymous groups should be flattened.
    :return: JSON Schema (dict).
    """
    if visited is None:
        visited = set()

    # Handle Union types (simple types with multiple types)
    if xsd_type.is_union():
        return convert_union_type(xsd_type)
    if xsd_type.is_simple():
        return convert_simple_type(xsd_type)
    else:
        return convert_complex_type(xsd_type, definitions, visited, flatten_anonymous)


def convert_union_type(xsd_type: XsdUnion):
    """
    Convert an xmlschema.XsdUnion into JSON Schema.
    """
    schema_obj = {"anyOf": []}

    if not hasattr(xsd_type, "member_types"):
        logger.warning(f"WARNING: Unexpected union type: {xsd_type}")
        return {"type": xsd_type.name}

    for member_type in xsd_type.member_types:
        member_schema = convert_xsd_type(member_type, {}, visited=set())
        schema_obj["anyOf"].append(member_schema)
    return schema_obj


def convert_simple_type(xsd_type: XsdType):
    """
    Convert an xmlschema.XsdSimpleType into JSON Schema: enumerations, patterns, etc.
    """
    schema_obj = {}

    # Handle nexted union types
    if xsd_type.is_union():
        return convert_union_type(xsd_type)

    # Handle AnySimpleType
    if xsd_type.name == r"{http://www.w3.org/2001/XMLSchema}anySimpleType":
        return {"type": ["string", "number", "boolean", "integer"]}

    if not hasattr(xsd_type, "primitive_type"):
        if xsd_type.is_list():
            # TODO: Handle list types
            pass
        logger.warning(f"WARNING: Unexpected simple type: {xsd_type}")
        return {"type": "string"}

    # Attempt to figure out the built-in base type
    base_type = xsd_type.primitive_type or xsd_type.base_type
    if base_type and base_type.name in xmlschema.XMLSchema.builtin_types():
        # We have something like "string", "boolean", etc.
        schema_obj["type"] = map_xsd_builtin_to_json_type(normalize_name(base_type))
    else:
        # If we don't have a built-in, default to string.
        schema_obj["type"] = "string"

    # Enumerations
    if xsd_type.enumeration:
        schema_obj["enum"] = list(xsd_type.enumeration)

    # Patterns
    if xsd_type.patterns:
        # xmlschema can store multiple patterns, but often there is just one
        patterns: xmlschema.validators.facets.XsdPatternFacets = xsd_type.patterns
        patterns = xsd_type.patterns
        pattern_obj: re.Pattern = patterns[0]
        schema_obj["pattern"] = pattern_obj.get("value")

    # Facets like minLength, maxLength, totalDigits, fractionDigits, etc.
    facets = xsd_type.facets
    if facets:
        if "minLength" in facets:
            schema_obj["minLength"] = facets["minLength"].value
        if "maxLength" in facets:
            schema_obj["maxLength"] = facets["maxLength"].value
        if "totalDigits" in facets:
            # no direct equivalent in JSON Schema, but some interpret totalDigits as maxLength
            schema_obj["maxLength"] = facets["totalDigits"].value
        # fractionDigits could be used to limit decimals, not directly in standard JSON Schema

        # numeric bounds: for integer types we can have minInclusive, maxInclusive
        # for dateTime and such, JSON Schema doesn't have direct equivalences, so might skip
        if "minInclusive" in facets:
            schema_obj["minimum"] = facets["minInclusive"].value
        if "maxInclusive" in facets:
            schema_obj["maximum"] = facets["maxInclusive"].value

    return schema_obj


def convert_complex_type(
    xsd_type: XsdComplexType, definitions, visited, flatten_anonymous=False
):
    """
    Convert an xmlschema.XsdComplexType into JSON Schema.
    """
    # If we've visited this type before (possible recursive definitions), return a reference.
    # But we only do this if it's a named type (with a qname).
    if xsd_type.name and xsd_type.name not in visited:
        visited.add(xsd_type.name)
    elif xsd_type.name and xsd_type.name in visited:
        # Return a $ref to the existing definition
        # because we've already defined it or are in the process of defining it.
        local_name = normalize_name(xsd_type)
        return {"$ref": f"#/definitions/{local_name}"}

    schema_obj = {
        "type": "object",
        "properties": {},
    }

    # Handle complex content with extension
    if xsd_type.has_complex_content():
        if xsd_type.derivation == "extension":
            base_schema = convert_xsd_type(
                xsd_type.base_type, definitions, visited, flatten_anonymous
            )
            # TODO: Base schema is already merged into schema_obj by convert_xsd_type, we should look at preventing this
            # so that we can just reference the base type.
            # schema_obj["allOf"] = [base_schema]

    required_list = []

    # 1. Handle attributes
    #    -----------------------------------------------------
    for attr_qname, attr in xsd_type.attributes.items():
        attr_name = normalize_name(attr)
        attr_schema = convert_attribute(attr)
        schema_obj["properties"][attr_name] = attr_schema
        if attr.use == "required":
            required_list.append(attr_name)

    # 2. Process the content model (elements, groups, choices, sequences, etc.)
    #    We'll do this explicitly so we can detect XsdGroup references.
    content_model = xsd_type.content
    if content_model:
        _handle_complex_content(
            content_model,
            schema_obj,
            definitions,
            visited,
            required_list,
            flatten_anonymous,
        )

    # 3. If this is a named type, store in definitions
    if xsd_type.name:
        local_name = normalize_name(xsd_type)
        definitions[local_name] = schema_obj

        if required_list:
            definitions[local_name]["required"] = sorted(set(required_list))

        return {"$ref": f"#/definitions/{local_name}"}

    # Otherwise, return inline
    if required_list:
        schema_obj["required"] = sorted(set(required_list))

    return schema_obj


def _handle_complex_content(
    xsd_component,
    parent_schema,
    definitions,
    visited,
    required_list,
    flatten_anonymous=False,
):
    """
    Recursively handle a complex content model, which can include elements, groups, sequences, etc.
    We modify parent_schema["properties"] to insert the generated properties.
    """
    # If it's an element, just handle it as a single element.
    if isinstance(xsd_component, XsdElement):
        elem_name = normalize_name(xsd_component)
        child_schema = convert_xsd_type(
            xsd_component.type, definitions, visited=visited
        )
        min_occurs = xsd_component.min_occurs
        max_occurs = xsd_component.max_occurs

        if (max_occurs is None) or (max_occurs > 1):
            child_schema = make_array_schema(child_schema, min_occurs, max_occurs)

        parent_schema["properties"][elem_name] = child_schema
        if min_occurs >= 1:
            required_list.append(elem_name)

    # If it's a group reference (XsdGroup, XsdSequenceGroup, XsdAllGroup, XsdChoiceGroup)
    elif isinstance(xsd_component, XsdGroup):
        # This might be a global group or an inline group (sequence, choice, all).
        group_schema = convert_xsd_group(
            xsd_component, definitions, visited, flatten_anonymous
        )

        # Because the group reference might have its own minOccurs/maxOccurs, we handle that here.
        # If group_schema is a $ref or an object, wrap it in an array if needed.
        min_occurs = getattr(xsd_component, "min_occurs", 1)
        max_occurs = getattr(xsd_component, "max_occurs", 1)

        # We'll store the group's result under a special property or
        # we might inline the group's properties.
        # A simple approach is to store them under the group's name if it has one:
        group_name = normalize_name(xsd_component) or "AnonymousGroup"

        if flatten_anonymous and group_name == "AnonymousGroup":
            parent_schema["properties"].update(group_schema.get("properties", {}))
            if "required" in group_schema:
                required_list.extend(group_schema["required"])
            if "oneOf" in group_schema:
                parent_schema.setdefault("oneOf", []).extend(group_schema["oneOf"])
            # merge any other keys like allOf, anyOf, etc., if needed
        else:
            if (max_occurs is None) or (max_occurs > 1):
                group_schema = make_array_schema(group_schema, min_occurs, max_occurs)
            parent_schema["properties"][group_name] = group_schema
            if min_occurs >= 1:
                required_list.append(group_name)
    else:
        logger.warning(f"WARNING: Unexpected content type: {xsd_component}")
    # If there's any other content type (like extension/restriction objects),
    # we can check xsd_component.content, etc. But for now we keep it simple.


def convert_attribute(xsd_attribute: XsdAttribute):
    """
    Convert an XsdAttribute into a JSON Schema snippet.
    """
    attr_schema = {}

    # Handle AnyAttribute
    if isinstance(xsd_attribute, XsdAnyAttribute):
        return {"type": "object", "additionalProperties": True}

    # The attribute has a type, typically XsdSimpleType
    t = xsd_attribute.type
    if t.is_simple():
        attr_schema.update(convert_simple_type(t))
    else:
        attr_schema["type"] = "string"

    # If attribute is 'fixed', represent that as "const"
    if xsd_attribute.fixed is not None:
        attr_schema["const"] = xsd_attribute.fixed

    return attr_schema


def convert_xsd_group(xsd_group, definitions, visited, flatten_anonymous=False):
    """
    Convert an xmlschema.XsdGroup (global or local) into a JSON Schema snippet.
    Groups often have a model: 'sequence', 'choice', or 'all'.
    """

    # Resolve group references first so we pick up the real group's children
    if hasattr(xsd_group, "ref") and xsd_group.ref and xsd_group.ref is not xsd_group:
        xsd_group = xsd_group.ref

    # Check for recursion
    if xsd_group.name and xsd_group.name not in visited:
        visited.add(xsd_group.name)
    elif xsd_group.name and xsd_group.name in visited:
        local_name = normalize_name(xsd_group)
        return {"$ref": f"#/definitions/{local_name}"}

    group_schema = {
        "type": "object",
        "properties": {},
    }
    required_list = []

    # Process group contents
    model = xsd_group.model
    if model in ("sequence", "all"):
        for child in xsd_group:
            if isinstance(child, XsdElement):
                elem_name = normalize_name(child)
                child_schema = convert_xsd_type(
                    child.type, definitions, visited, flatten_anonymous
                )

                if (child.max_occurs is None) or (child.max_occurs > 1):
                    child_schema = make_array_schema(
                        child_schema, child.min_occurs, child.max_occurs
                    )

                group_schema["properties"][elem_name] = child_schema
                if child.min_occurs >= 1:
                    required_list.append(elem_name)
            elif isinstance(child, XsdAnyElement):
                any_schema = convert_any_element(child)
                group_schema["properties"]["any"] = any_schema
            else:
                # Handle nested groups
                nested_schema = convert_xsd_group(
                    child, definitions, visited, flatten_anonymous
                )
                if isinstance(nested_schema, dict):
                    if "properties" in nested_schema:
                        group_schema["properties"].update(nested_schema["properties"])

                        # Add oneof to the parent schema
                        if "oneOf" in nested_schema:
                            if "oneOf" not in group_schema:
                                group_schema["oneOf"] = nested_schema["oneOf"]
                            else:
                                # Create a new property with the nested schema
                                # TODO: need to test this
                                group_name = normalize_name(child)
                                group_schema["properties"][group_name] = nested_schema
                                logger.warning(
                                    "Nested group with multiple oneOf's found in sequence/all group"
                                )

                        if "required" in nested_schema:
                            required_list.extend(nested_schema["required"])
                    elif hasattr(child, "ref") and child.ref:
                        group_name = normalize_name(child.ref)
                        group_schema["properties"][group_name] = {
                            "$ref": f"#/definitions/{group_name}"
                        }
                        if child.min_occurs >= 1:
                            required_list.append(group_name)
                    else:
                        raise ValueError(f"Unexpected nested schema: {nested_schema}")
                else:
                    raise ValueError(f"{nested_schema} is not a dict")
    elif model == "choice":
        one_of_list = []
        for child in xsd_group:
            choice_schema = {
                "type": "object",
                "properties": {},
            }
            sub_required = []

            if isinstance(child, XsdElement):
                elem_name = normalize_name(child)
                child_schema = convert_xsd_type(
                    child.type, definitions, visited, flatten_anonymous
                )

                if (child.max_occurs is None) or (child.max_occurs > 1):
                    child_schema = make_array_schema(
                        child_schema, child.min_occurs, child.max_occurs
                    )

                choice_schema["properties"][elem_name] = child_schema
                if child.min_occurs >= 1:
                    sub_required.append(elem_name)
            else:
                nested_schema = convert_xsd_group(
                    child, definitions, visited, flatten_anonymous
                )
                if isinstance(nested_schema, dict):
                    choice_schema["properties"].update(
                        nested_schema.get("properties", {})
                    )
                    if "required" in nested_schema:
                        sub_required.extend(nested_schema["required"])
            if sub_required:
                choice_schema["required"] = sorted(set(sub_required))
            one_of_list.append(choice_schema)

        group_schema["oneOf"] = one_of_list
    else:
        raise ValueError(f"Unexpected group model: {model}")

    # Store named groups in definitions
    if xsd_group.name:
        local_name = normalize_name(xsd_group)
        if required_list:
            group_schema["required"] = sorted(set(required_list))
        definitions[local_name] = group_schema
        return group_schema
    else:
        if required_list:
            group_schema["required"] = sorted(set(required_list))
        return group_schema


def convert_any_element(xsd_any):
    """Convert xs:any element to JSON Schema additionalProperties."""
    schema = {
        "type": "object",
        "additionalProperties": True,  # Default to allowing any properties
    }

    # Handle namespace constraints
    if xsd_any.namespace == "##other":
        # Could add namespace validation if needed
        pass
    elif xsd_any.namespace == "##any":
        pass

    # Handle processContents
    if xsd_any.process_contents == "skip":
        # No validation needed
        pass
    elif xsd_any.process_contents == "strict":
        # Would need schema validation
        pass

    return schema


##############################################################################
# MAIN SCRIPT
##############################################################################


def convert_xsd_to_jsonschema(xsd_file, out_file="schema.json", flatten_anonymous=True):
    # 1. Load the XSD
    logger.info(f"Parsing XSD: {xsd_file} with {flatten_anonymous=}")
    schema = xmlschema.XMLSchema(xsd_file)

    # 2. Prepare top-level JSON Schema structure
    json_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": os.path.basename(xsd_file).rsplit(".", 1)[0],
        "type": "object",
        "properties": {},
        "definitions": {},
    }

    # We'll keep track of visited QNames to avoid infinite recursion
    visited_qnames = set()

    # 3. Convert all global types into definitions
    for qname, xsd_type in schema.types.items():
        logger.info(f"Processing type: {qname}")
        if qname not in visited_qnames:
            convert_xsd_type(
                xsd_type,
                json_schema["definitions"],
                visited=visited_qnames,
                flatten_anonymous=flatten_anonymous,
            )

    # 3b. Convert all global model groups into definitions
    for group_qname, xsd_group in schema.groups.items():
        if group_qname not in visited_qnames:
            convert_xsd_group(
                xsd_group,
                json_schema["definitions"],
                visited=visited_qnames,
                flatten_anonymous=flatten_anonymous,
            )

    # 4. Convert global elements => top-level properties
    required_globals = []
    for qname, xsd_element in schema.elements.items():
        elem_name = normalize_name(xsd_element)
        elem_type = xsd_element.type

        prop_schema = convert_xsd_type(
            elem_type,
            json_schema["definitions"],
            visited=visited_qnames,
            flatten_anonymous=flatten_anonymous,
        )

        min_occurs = xsd_element.min_occurs
        max_occurs = xsd_element.max_occurs

        if (max_occurs is None) or (max_occurs > 1):
            prop_schema = make_array_schema(prop_schema, min_occurs, max_occurs)

        json_schema["properties"][elem_name] = prop_schema

        if min_occurs >= 1:
            required_globals.append(elem_name)

    if required_globals:
        json_schema["required"] = sorted(set(required_globals))

    # 5. Write out the final JSON Schema
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(json_schema, f, indent=2, ensure_ascii=False)

    logger.info(f"JSON Schema written to: {out_file}")
