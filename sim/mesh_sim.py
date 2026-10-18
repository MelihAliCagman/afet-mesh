import math
from dataclasses import dataclass


@dataclass
class Node:
    node_id: int
    x: float    # metre
    y: float    # metre
    is_gateway: bool = False


def distance(a: Node, b: Node) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


TX_POWER_DBM = 14.0
PATH_LOSS_D0_DB = 31.2
PATH_EXPONENT = 3.5
SENSITIVITY_DBM = -123.0


def rssi(a: Node, b: Node) -> float:
    d = max(distance(a, b), 1.0)
    return TX_POWER_DBM - PATH_LOSS_D0_DB - 10 * PATH_EXPONENT * math.log10(d)


def can_hear(tx: Node, rx: Node) -> bool:
    return rssi(tx, rx) >= SENSITIVITY_DBM


def neighbors(node: Node, nodes: list[Node]) -> list[Node]:
    return [
        other for other in nodes
        if other.node_id != node.node_id and can_hear(node, other)
    ]



