from wikidash.paths import normalize_page_name, reencode_component, split_file_path


def test_reencode_escapes_forbidden_characters() -> None:
    assert reencode_component('a:b*c?d"e<f>g|h\\i/j') == (
        "a%3Ab%2Ac%3Fd%22e%3Cf%3Eg%7Ch%5Ci%2Fj"
    )


def test_reencode_decodes_first() -> None:
    assert reencode_component("a%20b") == "a b"
    assert reencode_component("a%2Fb") == "a%2Fb"


def test_normalize_page_name() -> None:
    assert normalize_page_name("scp:001") == "scp_001"


def test_split_file_path() -> None:
    assert split_file_path("page/file.png") == ("page", "file.png")
    assert split_file_path("/file.png") == ("~", "file.png")
    assert split_file_path("file.png") == ("~", "file.png")
    assert split_file_path("p/..") == ("p", "why_did_you_name_me_this_way")
    assert split_file_path("../f") == ("why_did_you_name_me_this_way", "f")
