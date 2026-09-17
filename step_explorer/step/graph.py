"""Reference graph operations over one parsed STEP document."""

from collections.abc import Iterator
from dataclasses import dataclass

from .parser import StepDocument, StepEntity


@dataclass(frozen=True)
class GraphLink:
    source: int
    target: int


class ReferenceGraph:
    def __init__(self, document: StepDocument):
        self.document = document

    def outgoing_ids(self, entity_id: int) -> tuple[int, ...]:
        return self.document.outgoing.get(entity_id, ())

    def incoming_ids(self, entity_id: int) -> tuple[int, ...]:
        return self.document.incoming.get(entity_id, ())

    def outgoing_entities(self, entity_id: int) -> Iterator[StepEntity]:
        for target in self.outgoing_ids(entity_id):
            entity = self.document.entity(target)
            if entity is not None:
                yield entity

    def incoming_entities(self, entity_id: int) -> Iterator[StepEntity]:
        for source in self.incoming_ids(entity_id):
            entity = self.document.entity(source)
            if entity is not None:
                yield entity

    def walk(self, root_id: int, *, max_depth: int | None = None) -> Iterator[tuple[StepEntity, int]]:
        """Depth-first traversal, yielding each reachable entity once."""

        visited: set[int] = set()

        def visit(entity_id: int, depth: int) -> Iterator[tuple[StepEntity, int]]:
            if entity_id in visited or (max_depth is not None and depth > max_depth):
                return
            entity = self.document.entity(entity_id)
            if entity is None:
                return
            visited.add(entity_id)
            yield entity, depth
            for child in self.outgoing_ids(entity_id):
                yield from visit(child, depth + 1)

        yield from visit(root_id, 0)

