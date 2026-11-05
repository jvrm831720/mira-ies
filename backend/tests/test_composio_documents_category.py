from app.services.composio.categories import annotate_toolkit, documents_category


def test_document_toolkits_receive_category_metadata():
    expected = {
        "googledrive": ("Google Drive", "cloud_storage"),
        "one_drive": ("OneDrive", "cloud_storage"),
        "share_point": ("SharePoint", "document_collaboration"),
        "dropbox": ("Dropbox", "cloud_storage"),
    }

    for slug, (name, kind) in expected.items():
        annotated = annotate_toolkit({"slug": slug, "name": name})
        assert annotated["mira_category"] == "documents"
        assert annotated["mira_category_label"] == "Documentos e arquivos"
        assert annotated["mira_channel"] == kind


def test_documents_category_contains_only_verified_composio_toolkits():
    category = documents_category()
    slugs = {item["slug"] for item in category["composio_toolkits"]}

    assert category["slug"] == "documents"
    assert slugs == {"googledrive", "one_drive", "share_point", "dropbox"}
    assert category["native_channels"] == []


def test_unknown_file_provider_is_not_misrepresented_as_composio_toolkit():
    annotated = annotate_toolkit({"slug": "unverified_storage", "name": "Unknown Storage"})

    assert annotated["mira_category"] is None
    assert annotated["mira_category_label"] is None
