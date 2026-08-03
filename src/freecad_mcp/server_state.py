from dataclasses import dataclass

from .freecad_client import FreeCADConnection


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "localhost"
    vision_summary: bool = False
    vision_model: str = "llava:7b"
    vision_url: str = "http://localhost:11434"
    freecad_connection: FreeCADConnection | None = None
