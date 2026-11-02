from django.apps import apps
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ProjectState
from django.utils import translation


def test_initial_migration_uses_custom_account_and_swaps_default_user():
    loader = MigrationLoader(None)
    migration = loader.disk_migrations["identity", "0001_initial"]
    assert migration.initial
    assert len(migration.operations) == 1
    assert migration.operations[0].name == "Account"
    assert migration.operations[0].options["db_table"] == "identity_account"
    historical_apps = loader.project_state().apps
    assert historical_apps.get_model("identity", "Account")._meta.db_table == "identity_account"
    assert historical_apps.get_model("auth", "User")._meta.swapped == "identity.Account"


def test_migration_and_installed_models_have_no_changes():
    with translation.override(None):
        loader = MigrationLoader(None)
        changes = MigrationAutodetector(
            loader.project_state(), ProjectState.from_apps(apps)
        ).changes(graph=loader.graph)
    assert changes == {}
