"""``myScreens``, ``screenDetail`` and ``screenVersions`` over the golden API store (site presets
only): the user owns no screen yet, a site rule screen they have not copied reads as itself
(pinned to nothing, at its current version), and an unknown id is null, not an error. The
write-then-read flows are in ``tests/apps/api/routes/authoring/test_screeners.py``."""

from tests.apps.api.graphql.conftest import Graph

READS = """query R($id: String!) {
  myScreens { screenerId }
  screenDetail(screenerId: $id) {
    screenerId draft versions layers working preset { presetId pinned current rebaseAvailable }
  }
  screenVersions(screenerId: $id) { version }
}"""


def test_an_uncopied_site_preset_reads_as_itself(graph: Graph) -> None:
    body = graph(READS, {"id": "vrp_scanner"})
    assert "errors" not in body, body
    data = body["data"]
    assert data["myScreens"] == [] and data["screenVersions"] == []
    detail = data["screenDetail"]
    assert (detail["screenerId"], detail["draft"], detail["versions"]) == ("vrp_scanner", None, [])
    assert detail["preset"]["presetId"] == "vrp_scanner" and detail["preset"]["pinned"] is None
    assert detail["layers"] and detail["working"]["criteria"]


def test_an_unknown_screen_is_null(graph: Graph) -> None:
    body = graph(READS, {"id": "nothing"})
    assert "errors" not in body and body["data"]["screenDetail"] is None
    bad = graph(READS, {"id": "Not An Id"})
    assert bad["errors"][0]["extensions"]["code"] == "BAD_REQUEST"
