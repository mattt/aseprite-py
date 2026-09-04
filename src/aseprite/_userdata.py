"""User-data property encode and decode."""

from __future__ import annotations

from uuid import UUID

from aseprite._binary import Reader, Writer
from aseprite._errors import FormatError
from aseprite._model import PropertiesMap, PropertyType, UserData, UserProperty

_MAX_DEPTH = 128


def read_user_data(r: Reader) -> UserData:
    flags = r.u32()
    text: str | None = None
    color: tuple[int, int, int, int] | None = None
    properties: list[PropertiesMap] = []
    if flags & 1:
        text = r.string()
    if flags & 2:
        color = (r.u8(), r.u8(), r.u8(), r.u8())
    if flags & 4:
        start = r.pos
        size = r.u32()
        count = r.u32()
        for _ in range(count):
            key = r.u32()
            nprops = r.u32()
            props = [_read_property(r, 0) for _ in range(nprops)]
            properties.append(PropertiesMap(key=key, properties=props))
        consumed = r.pos - start
        if consumed < size:
            r.skip(size - consumed)
        elif consumed > size:
            raise FormatError("user-data properties exceed declared size")
    return UserData(text=text, color=color, properties=properties)


def write_user_data(w: Writer, data: UserData) -> None:
    flags = 0
    if data.text is not None:
        flags |= 1
    if data.color is not None:
        flags |= 2
    if data.properties:
        flags |= 4
    w.u32(flags)
    if data.text is not None:
        w.string(data.text)
    if data.color is not None:
        r, g, b, a = data.color
        w.u8(r)
        w.u8(g)
        w.u8(b)
        w.u8(a)
    if data.properties:
        size_at = w.tell()
        w.u32(0)
        w.u32(len(data.properties))
        for mapping in data.properties:
            w.u32(mapping.key)
            w.u32(len(mapping.properties))
            for prop in mapping.properties:
                _write_property(w, prop, 0)
        w.patch_u32(size_at, w.tell() - size_at)


def _read_property(r: Reader, depth: int) -> UserProperty:
    name = r.string()
    kind = PropertyType(r.u16())
    value = _read_value(r, kind, depth)
    return UserProperty(name=name, kind=kind, value=value)


def _write_property(w: Writer, prop: UserProperty, depth: int) -> None:
    w.string(prop.name)
    w.u16(int(prop.kind))
    _write_value(w, prop.kind, prop.value, depth)


def _read_value(r: Reader, kind: PropertyType, depth: int) -> object:
    if depth > _MAX_DEPTH:
        raise FormatError("user-data property nesting exceeds 128 levels")
    if kind is PropertyType.BOOL:
        return r.u8() != 0
    if kind is PropertyType.INT8:
        return r.i8()
    if kind is PropertyType.UINT8:
        return r.u8()
    if kind is PropertyType.INT16:
        return r.i16()
    if kind is PropertyType.UINT16:
        return r.u16()
    if kind is PropertyType.INT32:
        return r.i32()
    if kind is PropertyType.UINT32:
        return r.u32()
    if kind is PropertyType.INT64:
        return r.i64()
    if kind is PropertyType.UINT64:
        return r.u64()
    if kind is PropertyType.FIXED:
        return r.u32()
    if kind is PropertyType.FLOAT:
        return r.f32()
    if kind is PropertyType.DOUBLE:
        return r.f64()
    if kind is PropertyType.STRING:
        return r.string()
    if kind is PropertyType.POINT:
        return (r.i32(), r.i32())
    if kind is PropertyType.SIZE:
        return (r.i32(), r.i32())
    if kind is PropertyType.RECT:
        return (r.i32(), r.i32(), r.i32(), r.i32())
    if kind is PropertyType.VECTOR:
        count = r.u32()
        element = r.u16()
        if element == 0:
            values = []
            for _ in range(count):
                item_kind = PropertyType(r.u16())
                values.append((item_kind, _read_value(r, item_kind, depth + 1)))
            return (0, values)
        item_kind = PropertyType(element)
        values = [_read_value(r, item_kind, depth + 1) for _ in range(count)]
        return (element, values)
    if kind is PropertyType.PROPERTIES:
        nprops = r.u32()
        return [_read_property(r, depth + 1) for _ in range(nprops)]
    if kind is PropertyType.UUID:
        return UUID(bytes=r.uuid())
    raise FormatError(f"unsupported property type {int(kind):#06x}")


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    raise FormatError("property value must be an integer")


def _as_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise FormatError("property value must be a float")


def _as_pair(value: object) -> tuple[int, int]:
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(item, int) for item in value)
    ):
        return int(value[0]), int(value[1])
    raise FormatError("property value must be a pair of integers")


def _as_rect(value: object) -> tuple[int, int, int, int]:
    if (
        isinstance(value, tuple)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
    ):
        return int(value[0]), int(value[1]), int(value[2]), int(value[3])
    raise FormatError("property value must be a rectangle of integers")


def _write_value(w: Writer, kind: PropertyType, value: object, depth: int) -> None:
    if depth > _MAX_DEPTH:
        raise FormatError("user-data property nesting exceeds 128 levels")
    if kind is PropertyType.BOOL:
        w.u8(1 if value else 0)
    elif kind is PropertyType.INT8:
        w.i8(_as_int(value))
    elif kind is PropertyType.UINT8:
        w.u8(_as_int(value))
    elif kind is PropertyType.INT16:
        w.i16(_as_int(value))
    elif kind is PropertyType.UINT16:
        w.u16(_as_int(value))
    elif kind is PropertyType.INT32:
        w.i32(_as_int(value))
    elif kind is PropertyType.UINT32:
        w.u32(_as_int(value))
    elif kind is PropertyType.INT64:
        w.i64(_as_int(value))
    elif kind is PropertyType.UINT64:
        w.u64(_as_int(value))
    elif kind is PropertyType.FIXED:
        w.u32(_as_int(value))
    elif kind is PropertyType.FLOAT:
        w.f32(_as_float(value))
    elif kind is PropertyType.DOUBLE:
        w.f64(_as_float(value))
    elif kind is PropertyType.STRING:
        w.string(str(value))
    elif kind is PropertyType.POINT:
        x, y = _as_pair(value)
        w.i32(x)
        w.i32(y)
    elif kind is PropertyType.SIZE:
        width, height = _as_pair(value)
        w.i32(width)
        w.i32(height)
    elif kind is PropertyType.RECT:
        x, y, width, height = _as_rect(value)
        w.i32(x)
        w.i32(y)
        w.i32(width)
        w.i32(height)
    elif kind is PropertyType.VECTOR:
        if not isinstance(value, tuple) or len(value) != 2:
            raise FormatError("vector property must be (element_type, items)")
        element, items = value
        if not isinstance(items, list):
            raise FormatError("vector items must be a list")
        w.u32(len(items))
        w.u16(_as_int(element))
        if _as_int(element) == 0:
            for item in items:
                if not isinstance(item, tuple) or len(item) != 2:
                    raise FormatError("mixed vector items must be (type, value)")
                item_kind, item_value = item
                w.u16(_as_int(item_kind))
                _write_value(w, PropertyType(_as_int(item_kind)), item_value, depth + 1)
        else:
            item_kind = PropertyType(_as_int(element))
            for item in items:
                _write_value(w, item_kind, item, depth + 1)
    elif kind is PropertyType.PROPERTIES:
        if not isinstance(value, list):
            raise FormatError("nested properties must be a list")
        w.u32(len(value))
        for prop in value:
            if not isinstance(prop, UserProperty):
                raise FormatError("nested properties must be UserProperty values")
            _write_property(w, prop, depth + 1)
    elif kind is PropertyType.UUID:
        if isinstance(value, UUID):
            w.uuid(value.bytes)
        elif isinstance(value, bytes):
            w.uuid(value)
        else:
            raise FormatError("UUID property must be a UUID or 16 bytes")
    else:
        raise FormatError(f"unsupported property type {int(kind):#06x}")
