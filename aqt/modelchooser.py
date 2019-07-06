# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The window allowing to choose a model. Either for a card to add, to
import notes, or to change the model of a card.

"""

from aqt.qt import *
from anki.hooks import addHook, remHook, runHook
from aqt.utils import  shortcut
from anki.lang import _

class ModelChooser(QHBoxLayout):
    """
    label -- Whether this object corresponds to a button
    (i.e. note importer/addcards, but not browser.
    widget -- the button used to open this window. It contains the
    name of the current model.
    """
    def __init__(self, mw, widget, label=True, addCardWindow = None):
        QHBoxLayout.__init__(self)
        self.widget = widget
        self.mw = mw
        self.addCardWindow = addCardWindow
        self.deck = mw.col
        self.label = label
        self.setContentsMargins(0,0,0,0)
        self.setSpacing(8)
        self.setupModels()
        addHook('reset', self.onReset)
        self.widget.setLayout(self)

    def setupModels(self):
        if self.label:
            self.modelLabel = QLabel(_("Type"))
            self.addWidget(self.modelLabel)
        # models box
        self.models = QPushButton()
        #self.models.setStyleSheet("* { text-align: left; }")
        self.models.setToolTip(shortcut(_("Change Note Type (Ctrl+N)")))
        s = QShortcut(QKeySequence(_("Ctrl+N")), self.widget, activated=self.onModelChange)
        self.models.setAutoDefault(False)
        self.addWidget(self.models)
        self.models.clicked.connect(self.onModelChange)
        # layout
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy(7),
            QSizePolicy.Policy(0))
        self.models.setSizePolicy(sizePolicy)
        self.updateModels()

    def cleanup(self):
        remHook('reset', self.onReset)

    def onReset(self):
        """Change the button's text so that it has the name of the current
        model."""
        self.updateModels()

    def show(self):
        self.widget.show()

    def hide(self):
        self.widget.hide()

    def onEdit(self):
        import aqt.models
        aqt.models.Models(self.mw, self.widget)

    def onModelChange(self):
        """Open Choose Note Type window"""
        #Method called when we want to change the current model
        from aqt.studydeck import StudyDeck
        current = self.deck.models.current()['name']
        # edit button
        edit = QPushButton(_("Manage"), clicked=self.onEdit)
        def nameFunc():
            return sorted(self.deck.models.allNames())
        ret = StudyDeck(
            self.mw, names=nameFunc,
            accept=_("Choose"), title=_("Choose Note Type"),
            help="_notes", current=current, parent=self.widget,
            buttons=[edit], cancel=True, geomKey="selectModel")
        if not ret.name:
            return
        m = self.deck.models.byName(ret.name)
        self.deck.conf['curModel'] = m['id']
        cdeck = self.deck.decks.current()
        cdeck['mid'] = m['id']
        self.deck.decks.save(cdeck)
        if self.addCardWindow:
            runHook("currentModelChanged")
            self.mw.reset()
        else:
            self.addCardWindow.onModelChange() #this is onModelChange from card, and note from ModelChange
            self.updateModels()

    def updateModels(self):
        """Change the button's text so that it has the name of the current
        model."""
        if hasattr(self,"editor") or (self.addCardWindow is not None):#self's init has ended
            modelName=self.addCardWindow.editor.note._model["name"]
        else:# initialisation of the window
            modelName=self.deck.models.current()['name']
        self.models.setText(modelName)
