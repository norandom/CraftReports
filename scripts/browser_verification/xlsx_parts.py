"""Read-only bounded OOXML archive and relationship resolution."""

import posixpath
from pathlib import PurePosixPath
from stat import S_ISLNK
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "x": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
}
MAX_MEMBERS = 100
MAX_MEMBER_BYTES = 1_000_000
MAX_TOTAL_BYTES = 4_000_000


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def text_at(root: ET.Element, path: str) -> str:
    return root.findtext(path, default="", namespaces=NS)


def element(root: ET.Element, path: str) -> ET.Element:
    found = root.find(path, NS)
    require(found is not None, "missing-element")
    assert found is not None
    return found


class Parts:
    def __init__(self, archive: ZipFile) -> None:
        members = archive.infolist()
        names = [item.filename for item in members]
        require(0 < len(members) <= MAX_MEMBERS, "member-count")
        require(len(set(names)) == len(names), "duplicate-part")
        require(sum(item.file_size for item in members) <= MAX_TOTAL_BYTES, "expanded-size")
        self.xml: dict[str, ET.Element] = {}
        for item in members:
            name = item.filename
            require(not S_ISLNK(item.external_attr >> 16), "symlink-part")
            require(item.file_size <= MAX_MEMBER_BYTES, "member-size")
            require(self.safe_name(name), "unsafe-part-path")
            require(not item.flag_bits & 1, "encrypted-part")
            data = archive.read(item)
            if name.endswith((".xml", ".rels")):
                require(b"<!doctype" not in data.lower().replace(b"\x00", b""), "xml-dtd")
                require(b"<!entity" not in data.lower().replace(b"\x00", b""), "xml-entity")
                self.xml[name] = ET.fromstring(data)
        for name in self.xml:
            if name.endswith(".rels"):
                self.relationships(self.owner(name))

    @staticmethod
    def safe_name(name: str) -> bool:
        parts = PurePosixPath(name).parts
        return (
            bool(parts)
            and not name.startswith("/")
            and "%" not in name
            and "\x00" not in name
            and all(
                part not in ("..", ".") and ":" not in part and "\\" not in part
                for part in name.split("/")
            )
            and posixpath.normpath(name) == name
        )

    @staticmethod
    def owner(name: str) -> str:
        if name == "_rels/.rels":
            return ""
        parent, filename = posixpath.split(name)
        return posixpath.join(posixpath.dirname(parent), filename.removesuffix(".rels"))

    def root(self, name: str) -> ET.Element:
        require(name in self.xml, "missing-part")
        return self.xml[name]

    def relationships(self, owner: str) -> dict[str, tuple[str, str]]:
        directory, filename = posixpath.split(owner)
        name = posixpath.join(directory, "_rels", filename + ".rels")
        root = self.xml.get(name)
        if root is None:
            return {}
        result: dict[str, tuple[str, str]] = {}
        for rel in root.findall("p:Relationship", NS):
            require(rel.get("TargetMode", "Internal") == "Internal", "external-relationship")
            target = rel.get("Target", "")
            require(bool(target) and not target.startswith("//"), "unsafe-target")
            require(
                not any(token in target for token in ("\\", ":", "?", "#", "%")), "unsafe-target"
            )
            resolved = posixpath.normpath(posixpath.join(directory, target.lstrip("/")))
            if target.startswith("/"):
                resolved = target.lstrip("/")
            require(self.safe_name(resolved), "unsafe-target")
            key = rel.get("Id", "")
            require(bool(key) and key not in result, "duplicate-relationship")
            result[key] = (rel.get("Type", "").rsplit("/", 1)[-1], resolved)
        return result

    def related(self, owner: str, kind: str, key: str | None = None) -> str:
        matches = [
            path
            for ident, (role, path) in self.relationships(owner).items()
            if role == kind and (key is None or ident == key)
        ]
        require(len(matches) == 1, "missing-or-ambiguous-relationship")
        return matches[0]


def relation_id(node: ET.Element) -> str:
    return node.get("{" + NS["r"] + "}id", "")
