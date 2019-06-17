# -*- coding: utf-8 -*-
# Version: 2.5
# See github page to report issues or to contribute:
# https://github.com/hssm/anki-addons

from anki.hooks import wrap
from aqt import *
from aqt.addcards import AddCards
from aqt.editor import Editor
import aqt.editor
from . import config


# Flag to enable hack to make Frozen Fields look normal

__location__ = os.path.realpath(
    os.path.join(os.getcwd(), os.path.dirname(__file__)))
js_file = os.path.join(__location__,"js.js")
user_files = os.path.join(__location__,"user_files")
css_file = os.path.join(user_files,"css.css")
with open(js_file,"r") as f:
    js= f.read()

with open(css_file,"r") as f:
    css= f.read()

aqt.editor._html += f"""<style>{css}</style><script>{js}</script>"""
aqt.editor._html += f"""<script>{js}</script>"""

def onColumnCountChanged(self, count):
    "Save column count to settings and re-draw with new count."
    config.setConfig("count", count, self.note.mid, self.parentWindow.__class__.__name__)
    self.loadNote()

def myEditorInit(self, mw, widget, parentWindow, addMode=False):
    self.ccSpin = QSpinBox(self.widget)
F    b = QPushButton(u"▾")
    b.clicked.connect(lambda: onConfigClick(self))
    b.setFixedHeight(self.tags.height())
    b.setFixedWidth(25)
    b.setAutoDefault(False)
    hbox = QHBoxLayout()
    hbox.setSpacing(0)
    label = QLabel("Columns:", self.widget)
    hbox.addWidget(label)
    hbox.addWidget(self.ccSpin)
    hbox.addWidget(b)

    self.ccSpin.setMinimum(1)
    self.ccSpin.setMaximum(config.getConfig("MAX_COLUMNS", 18))
    self.ccSpin.valueChanged.connect(lambda value: onColumnCountChanged(self, value))

    # We will place the column count editor next to the tags widget.
    pLayout = self.tags.parentWidget().layout()
    # Get the indices of the tags widget
    (rIdx, cIdx, r, c) = pLayout.getItemPosition(pLayout.indexOf(self.tags))
    # Place ours on the same row, to its right.
    pLayout.addLayout(hbox, rIdx, cIdx+1)

    # If the user has the Frozen Fields add-on installed, tweak the
    # layout a bit to make it look right.
    print(f"""self.parentWindow is {self.parentWindow} of type {type(self.parentWindow)}""")
    if config.getConfig("Frozen Fields number", "516643804") in mw.addonManager.allAddons() and isinstance(self.parentWindow, AddCards):
        self.ffFix = True
    else:
        self.ffFix = False


def myOnBridgeCmd(self, cmd):
    """
    Called from JavaScript to inject some values before it needs
    them.
    """
    if cmd == "mceTrigger":
        count = config.getConfig("count", 1, self.note.mid, self.parentWindow.__class__.__name__)
        self.web.eval(f"setColumnCount({count});")
        self.ccSpin.blockSignals(True)
        self.ccSpin.setValue(count)
        self.ccSpin.blockSignals(False)
        for fld, val in self.note.items():
            if config.getConfig(fld, False, self.note.mid, self.parentWindow.__class__.__name__):
                self.web.eval(f"setSingleLine('{fld}');")
        self.web.eval("makeColumns2()")

def onConfigClick(self):
    m = QMenu(self.mw)
    def addCheckableAction(menu, isCheck, fld):
        a = menu.addAction(fld)
        a.setCheckable(True)
        a.setChecked(isCheck)
        a.toggled.connect(lambda b, f=fld: onCheck(self, f))

    # Descriptive title thing
    a = QAction(u"―Single Row―", m)
    a.setEnabled(False)
    m.addAction(a)

    for fld, val in self.note.items():
        isCheck = config.getConfig(fld, False, mid =  self.note.mid, windowName = self.parentWindow.__class__.__name__)
        addCheckableAction(m, isCheck, fld)

    m.exec_(QCursor.pos())


def onCheck(self, field):
    current = config.getConfig(field, mid = self.note.mid, windowName = self.parentWindow.__class__.__name__)
    config.setConfig(field, not current, mid = self.note.mid, windowName = self.parentWindow.__class__.__name__)
    self.loadNote()


Editor.__init__ = wrap(Editor.__init__, myEditorInit)
Editor.onBridgeCmd = wrap(Editor.onBridgeCmd, myOnBridgeCmd, 'before')
