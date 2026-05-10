import time
import pytest
from freecad_mcp.freecad_client import FreeCADConnection


@pytest.fixture(scope="session")
def conn():
    c = FreeCADConnection()
    try:
        result = c.ping()
    except Exception:
        pytest.skip("FreeCAD RPC server not reachable")
    if not result:
        pytest.skip("FreeCAD RPC server ping returned False")
    yield c
    c.disconnect()


@pytest.fixture
def doc(conn):
    name = f"Test_{int(time.time() * 1000)}"
    result = conn.create_document(name)
    assert result.get("success"), f"Failed to create document: {result.get('error')}"
    yield name
    conn.execute_code(f"import FreeCAD; FreeCAD.closeDocument('{name}')")


@pytest.fixture
def no_screenshot():
    return lambda response, screenshot: response


@pytest.fixture
def mock_ctx():
    class _Ctx:
        pass
    return _Ctx()
