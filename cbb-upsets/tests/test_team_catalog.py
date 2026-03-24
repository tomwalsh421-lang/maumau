import sqlite3

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


def test_load_team_catalog_adds_conference_metadata_from_team_details() -> None:
    from cbb.team_catalog import load_team_catalog

    class FakeEspnClient:
        def get_teams(self, *, group: str = "50", limit: int = 500):
            del group, limit
            return [
                {
                    "id": "2",
                    "location": "Auburn",
                    "displayName": "Auburn Tigers",
                }
            ]

        def get_team_details(self, team_id: str):
            assert team_id == "2"
            return {"standingSummary": "11th in SEC"}

    catalog = load_team_catalog(FakeEspnClient())

    auburn = catalog.resolve_team_name("Auburn Tigers")
    assert auburn is not None
    assert auburn.conference_key == "sec"
    assert auburn.conference_name == "SEC"


def test_load_team_catalog_keeps_recent_former_d1_supplemental_teams() -> None:
    from cbb.team_catalog import load_team_catalog

    class FakeEspnClient:
        def get_teams(self, *, group: str = "50", limit: int = 500):
            del group, limit
            return []

        def get_team_details(self, team_id: str):
            raise AssertionError(f"unexpected team detail lookup: {team_id}")

    catalog = load_team_catalog(FakeEspnClient())

    hartford = catalog.resolve_team_name("Hartford Hawks")
    assert hartford is not None
    assert hartford.display_name == "Hartford Hawks"

    st_francis_brooklyn = catalog.resolve_team_name("St. Francis (BKN) Terriers")
    assert st_francis_brooklyn is not None
    assert st_francis_brooklyn.display_name == "St. Francis Brooklyn Terriers"


def test_load_team_catalog_from_database_uses_stored_aliases_and_conference(
    tmp_path,
) -> None:
    from sqlalchemy import create_engine

    from cbb.team_catalog import load_team_catalog_from_database

    db_path = tmp_path / "team_catalog.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            conference_key TEXT,
            conference_name TEXT
        );

        CREATE TABLE team_aliases (
            team_alias_id INTEGER PRIMARY KEY,
            team_id INTEGER NOT NULL,
            alias_key TEXT NOT NULL UNIQUE,
            alias_name TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO teams (
            team_id, team_key, name, conference_key, conference_name
        ) VALUES (
            1,
            'michigan-state-spartans',
            'Michigan State Spartans',
            'big-ten',
            'Big Ten'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO team_aliases (team_id, alias_key, alias_name)
        VALUES (1, 'michigan-state', 'Michigan State')
        """
    )
    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite+pysqlite:///{db_path}", future=True)
    with engine.begin() as db_connection:
        catalog = load_team_catalog_from_database(db_connection)

    assert catalog is not None
    resolved_team = catalog.resolve_team_name("Michigan State")
    assert resolved_team is not None
    assert resolved_team.display_name == "Michigan State Spartans"
    assert resolved_team.conference_key == "big-ten"
    assert resolved_team.conference_name == "Big Ten"
