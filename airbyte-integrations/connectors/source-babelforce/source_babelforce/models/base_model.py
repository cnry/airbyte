from pydantic import BaseModel as PydanticBaseModel


class BaseModel(PydanticBaseModel):
    class Config:
        @staticmethod
        def schema_extra(schema, model):
            for prop, value in schema.get("properties", {}).items():
                field = [x for x in model.__fields__.values() if x.alias == prop][0]
                if field.allow_none:
                    if "type" in value:
                        value["anyOf"] = [{"type": value.pop("type")}]
                    elif "$ref" in value:
                        if issubclass(field.type_, PydanticBaseModel):
                            value["title"] = field.type_.__config__.title or field.type_.__name__
                        value["anyOf"] = [{"$ref": value.pop("$ref")}]
                    value["anyOf"].append({"type": "null"})
