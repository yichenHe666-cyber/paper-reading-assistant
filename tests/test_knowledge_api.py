from app.routes.knowledge import router


def test_knowledge_router_exists():
    assert router is not None
    assert hasattr(router, "routes")
    assert len(router.routes) > 0


def test_knowledge_routes_defined():
    expected_routes = {
        ("/upload", "POST"),
        ("/batch-import", "POST"),
        ("/documents", "GET"),
        ("/documents/{document_id}", "GET"),
        ("/documents/{document_id}", "DELETE"),
        ("/query", "POST"),
        ("/graph", "GET"),
        ("/graph/edges", "POST"),
        ("/graph/edges/{edge_id}", "PUT"),
        ("/graph/edges/{edge_id}", "DELETE"),
        ("/stats", "GET"),
        ("/extract/{document_id}", "POST"),
        ("/lint", "POST"),
    }

    registered = set()
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            for method in methods:
                registered.add((path, method))

    for path, method in expected_routes:
        assert (path, method) in registered, f"Missing route: {method} {path}"
