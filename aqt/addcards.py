# Copyright: Ankitects Pty Ltd and contributors
# -*- coding: utf-8 -*-
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""The window obtained from main by pressing A, or clicking on "Add"."""
from anki.lang import _

from aqt.qt import *
import aqt.forms
from aqt.utils import saveGeom, restoreGeom, showWarning, askUser, shortcut, \
    tooltip, openHelp, addCloseShortcut, downArrow
from anki.sound import clearAudioQueue
from anki.hooks import addHook, remHook, runHook
from anki.utils import htmlToTextLine, isMac
import aqt.editor, aqt.modelchooser, aqt.deckchooser

class AddCards(QDialog):

    def __init__(self, mw):
        QDialog.__init__(self, None, Qt.Window)
        mw.setupDialogGC(self)
        self.mw = mw
        self.form = aqt.forms.addcards.Ui_Dialog()
        self.form.setupUi(self)
        self.setWindowTitle(_("Add"))
        self.setMinimumHeight(300)
        self.setMinimumWidth(400)
        self.setupChoosers()
        self.setupEditor()
        self.setupButtons()
        self.onReset()
        self.history = []
        restoreGeom(self, "add")
        addHook("reset",lambda: self.onResetSameModel)
        addCloseShortcut(self)
        self.show()

    def setupEditor(self):
        self.editor = aqt.editor.Editor(
            self.mw, self.form.fieldsArea, self, True)

    def setupChoosers(self):
        self.modelChooser = aqt.modelchooser.ModelChooser(
            self.mw, self.form.modelArea, addCardWindow = self)
        self.deckChooser = aqt.deckchooser.DeckChooser(
            self.mw, self.form.deckArea)

    def helpRequested(self):
        openHelp("addingnotes")

    def setupButtons(self):
        bb = self.form.buttonBox
        ar = QDialogButtonBox.ActionRole
        # add
        self.addButton = bb.addButton(_("Add"), ar)
        self.addButton.clicked.connect(self.addCards)
        self.addButton.setShortcut(QKeySequence("Ctrl+Return"))
        self.addButton.setToolTip(shortcut(_("Add (shortcut: ctrl+enter)")))
        # close
        self.closeButton = QPushButton(_("Close"))
        self.closeButton.setAutoDefault(False)
        bb.addButton(self.closeButton, QDialogButtonBox.RejectRole)
        # help
        self.helpButton = QPushButton(_("Help"), clicked=self.helpRequested)
        self.helpButton.setAutoDefault(False)
        bb.addButton(self.helpButton,
                                        QDialogButtonBox.HelpRole)
        # history
        b = bb.addButton(
            _("History")+ " "+downArrow(), ar)
        if isMac:
            sc = "Ctrl+Shift+H"
        else:
            sc = "Ctrl+H"
        b.setShortcut(QKeySequence(sc))
        b.setToolTip(_("Shortcut: %s") % shortcut(sc))
        b.clicked.connect(self.onHistory)
        b.setEnabled(False)
        self.historyButton = b

    def setAndFocusNote(self, note):
        """Add note as the content of the editor. Focus in the first element."""
        self.editor.setNote(note, focusTo=0)

    def onModelChange(self):
        oldNote = self.editor.note
        note = self.mw.col.newNote()
        if oldNote:
            oldFields = list(oldNote.keys())
            newFields = list(note.keys())
            for n, f in enumerate(note.model()['flds']):
                fieldName = f['name']
                try:
                    oldFieldName = oldNote.model()['flds'][n]['name']
                except IndexError:
                    oldFieldName = None
                # copy identical fields
                if fieldName in oldFields:
                    note[fieldName] = oldNote[fieldName]
                # set non-identical fields by field index
                elif oldFieldName and oldFieldName not in newFields:
                    try:
                        note.fields[n] = oldNote.fields[n]
                    except IndexError:
                        pass
            self.removeTempNote(oldNote)
        self.editor.setNote(note)

    def onResetSameModel(self,keep=False):
        return self.onReset(model=self.editor.note._model, keep=keep)

    def onReset(self, model=None, keep=False):
        """Create a new note and set it with the current field values.

        keyword arguments
        model -- not used
        keep -- Whether the old note was saved in the collection. In
        this case, remove non sticky fields. Otherwise remove the last
        temporary note (it is replaced by a new one).
        """
        #Called with keep set to True from  _addCards
        #Called with default keep __init__, from hook "reset"
        #Meaning of the word keep guessed. Not clear.
        oldNote = self.editor.note
        if model is None:
            note = self.mw.col.newNote()
        else:#Difference is here. If model given as argument, it is used
            note = Note(self.mw.col, model=model)
        flds = note.model()['flds']
        # copy fields from old note
        if oldNote:
            if not keep:
                self.removeTempNote(oldNote)
            for n in range(len(note.fields)):
                try:
                    if not keep or flds[n]['sticky']:
                        note.fields[n] = oldNote.fields[n]
                    else:
                        note.fields[n] = ""
                except IndexError:
                    break
        self.setAndFocusNote(note)

    def removeTempNote(self, note):
        if not note or not note.id:
            return
        # we don't have to worry about cards; just the note
        self.mw.col._remNotes([note.id])

    def addHistory(self, note):
        self.history.insert(0, note.id)
        self.history = self.history[:15]
        self.historyButton.setEnabled(True)

    def onHistory(self):
        m = QMenu(self)
        for nid in self.history:
            if self.mw.col.findNotes("nid:%s" % nid):
                fields = self.mw.col.getNote(nid).fields
                txt = htmlToTextLine(", ".join(fields))
                if len(txt) > 30:
                    txt = txt[:30] + "..."
                a = m.addAction(_("Edit \"%s\"") % txt)
                a.triggered.connect(lambda b, nid=nid: self.editHistory(nid))
            else:
                a = m.addAction(_("(Note deleted)"))
                a.setEnabled(False)
        runHook("AddCards.onHistory", self, m)
        m.exec_(self.historyButton.mapToGlobal(QPoint(0,0)))

    def editHistory(self, nid):
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.form.searchEdit.lineEdit().setText("nid:%d" % nid)
        browser.onSearchActivated()

    def addNote(self, note):
        note.model()['did'] = self.deckChooser.selectedId()
        ret = note.dupeOrEmpty()
        if ret == 1:
            showWarning(_(
                "The first field is empty."),
                help="AddItems#AddError")
            return
        if '{{cloze:' in note.model()['tmpls'][0]['qfmt']:
            if not self.mw.col.models._availClozeOrds(
                    note.model(), note.joinedFields(), False):
                if not askUser(_("You have a cloze deletion note type "
                "but have not made any cloze deletions. Proceed?")):
                    return
        cards = self.mw.col.addNote(note)
        if not cards:
            showWarning(_("""\
The input you have provided would make an empty \
question on all cards."""), help="AddItems")
            return
        self.addHistory(note)
        self.mw.requireReset()
        return note

    def addCards(self):
        """Adding the content of the fields as a new note"""
        #Save edits in the fields, and call _addCards
        self.editor.saveNow(self._addCards)

    def _addCards(self):
        """Adding the content of the fields as a new note.

        Assume that the content of the GUI saved in the model."""
        self.editor.saveAddModeVars()
        note = self.editor.note
        note = self.addNote(note)
        if not note:
            return
        tooltip(_("Added"), period=500)
        # stop anything playing
        clearAudioQueue()
        self.onResetSameModel(keep=True)
        self.mw.col.autosave()

    def keyPressEvent(self, evt):
        "Show answer on RET or register answer."
        if (evt.key() in (Qt.Key_Enter, Qt.Key_Return)
            and self.editor.tags.hasFocus()):
            evt.accept()
            return
        return QDialog.keyPressEvent(self, evt)

    def reject(self):
        """Close the window.

        If data would be lost, ask for confirmation"""
        self.ifCanClose(self._reject)

    def _reject(self):
        """Close the window.

        Don't check whether data will be lost"""
        remHook('reset', self.onResetSameModel)
        remHook('currentModelChanged', self.onModelChange)
        clearAudioQueue()
        self.removeTempNote(self.editor.note)
        self.editor.cleanup()
        self.modelChooser.cleanup()
        self.deckChooser.cleanup()
        self.mw.maybeReset()
        saveGeom(self, "add")
        aqt.dialogs.markClosed("AddCards")
        QDialog.reject(self)

    def ifCanClose(self, onOk):
        def afterSave():
            ok = (self.editor.fieldsAreBlank() or
                    askUser(_("Close and lose current input?")))
            if ok:
                onOk()

        self.editor.saveNow(afterSave)

    def closeWithCallback(self, cb):
        def doClose():
            self._reject()
            cb()
        self.ifCanClose(doClose)
