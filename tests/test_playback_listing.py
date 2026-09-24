from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QComboBox

from step_explorer.step.parser import parse_step
from step_explorer.ui.entity_tree import EntityTree
from step_explorer.ui.main_window import MainWindow


def _document():
    return parse_step(
        "ISO-10303-21;\nDATA;\n"
        "#20=CARTESIAN_POINT('',(0.,0.,0.));\n"
        "#3=APPROVAL_STATUS('ok');\n"
        "#11=VERTEX_POINT('',#20);\n"
        "ENDSEC;\nEND-ISO-10303-21;\n"
    )


def test_playback_listing_shows_every_record_in_file_order(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    tree = EntityTree()
    tree.set_document(_document(), "Playback", geometry_only=True)

    assert [tree.topLevelItem(index).text(0) for index in range(tree.topLevelItemCount())] == [
        "3", "4", "5",
    ]
    assert tree.headerItem().text(0) == "Line"
    assert tree.headerItem().text(1) == "STEP source"
    assert tree.topLevelItem(1).text(1) == "#3=APPROVAL_STATUS('ok');"
    tree.focus_playback_entity(11)
    assert tree.currentItem().text(0) == "5"
    tree.close()
    assert app is not None


def test_play_switches_to_playback_listing(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    mode = QComboBox()
    mode.addItems(["File order", "Semantic", "Playback"])
    mode.setCurrentText("Semantic")
    tree = SimpleNamespace(focus_playback_entity=Mock())
    window = SimpleNamespace(
        document=_document(), playback_order=0, mode=mode, tree=tree,
        playback_timer=SimpleNamespace(start=Mock()),
        play_button=SimpleNamespace(setText=Mock()),
    )

    MainWindow._playback_toggled(window, True)

    assert mode.currentText() == "Playback"
    tree.focus_playback_entity.assert_called_once_with(20)
    window.playback_timer.start.assert_called_once()
    mode.close()
    assert app is not None


def test_clicking_playback_record_pauses_and_seeks(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    mode = QComboBox()
    mode.addItems(["File order", "Semantic", "Playback"])
    mode.setCurrentText("Playback")
    window = SimpleNamespace(
        document=_document(), mode=mode,
        play_button=SimpleNamespace(setChecked=Mock()),
        _set_playback_order=Mock(),
    )

    MainWindow._tree_entity_selected(window, 11)

    window.play_button.setChecked.assert_called_once_with(False)
    window._set_playback_order.assert_called_once_with(2)
    mode.close()
    assert app is not None
