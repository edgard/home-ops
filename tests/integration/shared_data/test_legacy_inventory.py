"""File consumers remain backed up until they adopt native capture."""


def registry():
    return {
        "version": 1,
        "consumers": {
            "selected": {
                "enabled": True,
                "backend": "postgresql",
                "pvcs": ["selfhosted/selected"],
            },
            "old": {"enabled": False, "backend": "sqlite", "pvcs": ["selfhosted/old"]},
            "adopted": {
                "enabled": True,
                "backend": "postgresql",
                "pvcs": ["selfhosted/adopted"],
            },
            "future": {
                "enabled": False,
                "backend": "postgresql",
                "pvcs": ["selfhosted/future"],
            },
        },
        "file_consumers": {
            "files": {"namespace": "selfhosted", "pvcs": ["selfhosted/files"]}
        },
    }


def test_only_source_owned_legacy_files_are_included(adapters):
    data = registry()
    assert adapters["data_tools"].legacy_pvcs(data, ["selected"]) == [
        "selfhosted/files",
        "selfhosted/old",
    ]
    assert adapters["data_tools"].legacy_pvcs(data, ["selected", "old"]) == [
        "selfhosted/files"
    ]
    data["consumers"]["old"]["enabled"] = True
    assert adapters["data_tools"].legacy_pvcs(data, ["selected"]) == [
        "selfhosted/files"
    ]
