from hermes_feishu_card.server import _compute_element_deltas


def test_no_changes_returns_empty():
    card = {
        "body": {
            "elements": [
                {"tag": "markdown", "element_id": "main", "content": "hello"},
                {"tag": "hr", "element_id": "divider"},
            ]
        }
    }
    assert _compute_element_deltas(card, card) == {}


def test_detects_changed_content():
    old = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "old"},
        {"tag": "markdown", "element_id": "footer", "content": "1s"},
    ]}}
    new = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "new text"},
        {"tag": "markdown", "element_id": "footer", "content": "1s"},
    ]}}
    deltas = _compute_element_deltas(old, new)
    assert deltas == {"main": "new text"}


def test_detects_new_element():
    old = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "hello"},
    ]}}
    new = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "hello"},
        {"tag": "markdown", "element_id": "tool", "content": "tools: 3"},
    ]}}
    deltas = _compute_element_deltas(old, new)
    assert deltas == {"tool": "tools: 3"}


def test_ignores_non_string_content():
    old = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "hello"},
    ]}}
    new = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "hello"},
        {"tag": "hr", "element_id": "divider"},
    ]}}
    deltas = _compute_element_deltas(old, new)
    assert deltas == {}


def test_missing_body_returns_empty():
    assert _compute_element_deltas({}, {}) == {}
    assert _compute_element_deltas({"body": {}}, {"body": {}}) == {}


def test_all_elements_changed():
    old = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "a"},
        {"tag": "markdown", "element_id": "footer", "content": "b"},
    ]}}
    new = {"body": {"elements": [
        {"tag": "markdown", "element_id": "main", "content": "x"},
        {"tag": "markdown", "element_id": "footer", "content": "y"},
    ]}}
    deltas = _compute_element_deltas(old, new)
    assert deltas == {"main": "x", "footer": "y"}
