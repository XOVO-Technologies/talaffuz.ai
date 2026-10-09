from app.models import ProcessingSettings, Project
from app.store import ProjectStore


def save(root, pid, settings, last_export=None):
    project = Project(id=pid, name=pid, created_at=0, settings=settings, last_export=last_export)
    (root / pid).mkdir(parents=True)
    (root / pid / "project.json").write_text(project.model_dump_json(), encoding="utf-8")


def test_projects_saved_with_the_old_default_range_move_to_the_generic_defaults(tmp_path):
    save(tmp_path, "old", ProcessingSettings(start_index=31, end_index=500))
    store = ProjectStore(tmp_path)
    s = store.get("old").settings
    assert (s.start_index, s.end_index) == (1, None)
    # the change is written back, so it survives a restart
    assert '"end_index":null' in (tmp_path / "old" / "project.json").read_text(encoding="utf-8").replace(" ", "")


def test_other_ranges_and_exported_projects_are_left_alone(tmp_path):
    save(tmp_path, "custom", ProcessingSettings(start_index=101, end_index=300))
    save(tmp_path, "exported", ProcessingSettings(start_index=31, end_index=500), last_export={"written": True})
    store = ProjectStore(tmp_path)
    assert (store.get("custom").settings.start_index, store.get("custom").settings.end_index) == (101, 300)
    assert (store.get("exported").settings.start_index, store.get("exported").settings.end_index) == (31, 500)
