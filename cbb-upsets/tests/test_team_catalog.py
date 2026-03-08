from tests.support import make_team_catalog


def test_team_catalog_resolves_common_provider_aliases() -> None:
    catalog = make_team_catalog(
        [
            ("Michigan State", "Michigan State Spartans", None),
            ("Seattle U", "Seattle U Redhawks", None),
            ("American University", "American University Eagles", ("American Eagles",)),
        ]
    )

    assert catalog.resolve_team_name("Michigan St Spartans").display_name == (
        "Michigan State Spartans"
    )
    assert catalog.resolve_team_name("Seattle Redhawks").display_name == (
        "Seattle U Redhawks"
    )
    assert catalog.resolve_team_name("American Eagles").display_name == (
        "American University Eagles"
    )


def test_team_catalog_rejects_non_d1_partial_matches() -> None:
    catalog = make_team_catalog([("Auburn", "Auburn Tigers", None)])

    assert catalog.resolve_team_name("Auburn-Montgomery Senators") is None
