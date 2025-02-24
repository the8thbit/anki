# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
mw -- the main window
col -- the collection
frm -- the formula GUIn
exporters -- A list of pairs (description of an exporter class, the class)
exporter -- An instance of the class choosen in the GUI
decks -- The list of decks option used in the GUI. All Decks and decks' name
isApkg -- Whether exporter's suffix is apkg
isVerbatim -- Whether exporter has an attribute "verbatim" set to True. Occurs only in Collection package exporter.
isTextNote -- Whether exporter has an attribute "includeTags" set to True. Occurs only in textNoteExporter.
"""

import os
import re

from aqt.qt import *
import  aqt
from aqt.utils import getSaveFile, tooltip, showWarning, \
    checkInvalidFilename, showInfo
from anki.exporting import exporters
from anki.hooks import addHook, remHook
from anki.lang import ngettext, _
import time

class ExportDialog(QDialog):

    def __init__(self, mw, did=None, cids=None):
        """
        cids -- the cards selected, if it's opened from the browser
        """
        QDialog.__init__(self, mw, Qt.Window)
        self.mw = mw
        self.cids = cids
        self.col = mw.col
        self.frm = aqt.forms.exporting.Ui_ExportDialog()
        self.frm.setupUi(self)
        self.exporter = None
        self.setup(did, cids)
        self.exec_()

    def setup(self, did = None, cids = None):
        """Set the GUI such that, by default, it exports whole collection. Or deck did. Or cards cids.

        keyword arguments:
        did -- If did is not None, export this deck.
        cids -- If cids is not None, export those cards.

        """
        self.exporters = exporters()
        # if a deck specified, start with .apkg type selected
        idx = 0
        if did or cids:
            for c, (k,e) in enumerate(self.exporters):
                if e.ext == ".apkg":
                    idx = c
                    break
        self.frm.format.insertItems(0, [e[0] for e in self.exporters])
        self.frm.format.setCurrentIndex(idx)
        self.frm.format.activated.connect(self.exporterChanged)
        self.exporterChanged(idx)
        # deck list
        self.decks = [_("All Decks")]
        if cids:
            bs=_("Browser's selection")
            self.decks.append(bs)
        self.decks = self.decks + sorted(self.col.decks.allNames())
        self.frm.deck.addItems(self.decks)
        # save button
        b = QPushButton(_("Export..."))
        self.frm.buttonBox.addButton(b, QDialogButtonBox.AcceptRole)
        # set default option if accessed through deck button
        if did:
            name = self.mw.col.decks.get(did)['name']
            index = self.frm.deck.findText(name)
            self.frm.deck.setCurrentIndex(index)

    def exporterChanged(self, idx):
        self.exporter = self.exporters[idx][1](self.col)
        self.isApkg = self.exporter.ext == ".apkg"
        self.isVerbatim = getattr(self.exporter, "verbatim", False)
        self.isTextNote = hasattr(self.exporter, "includeTags")
        self.frm.includeSched.setVisible(
            getattr(self.exporter, "includeSched", None) is not None)
        self.frm.includeMedia.setVisible(
            getattr(self.exporter, "includeMedia", None) is not None)
        self.frm.includeTags.setVisible(
            getattr(self.exporter, "includeTags", None) is not None)
        html = getattr(self.exporter, "includeHTML", None)
        if html is not None:
            self.frm.includeHTML.setVisible(True)
            self.frm.includeHTML.setChecked(html)
        else:
            self.frm.includeHTML.setVisible(False)
        # show deck list?
        self.frm.deck.setVisible(not self.isVerbatim)

    def accept(self):
        self.exporter.includeSched = (
            self.frm.includeSched.isChecked())
        self.exporter.includeMedia = (
            self.frm.includeMedia.isChecked())
        self.exporter.includeTags = (
            self.frm.includeTags.isChecked())
        self.exporter.includeHTML = (
            self.frm.includeHTML.isChecked())
        if self.frm.deck.currentIndex() == 0: #position 0 means: all decks.
            self.exporter.did = None
            self.exporter.cids = None
        elif self.frm.deck.currentIndex() == 1 and self.cids is not None:#position 1 means: selected decks.
            self.exporter.did = None
            self.exporter.cids = self.cids
        else:
            self.exporter.cids = None
            name = self.decks[self.frm.deck.currentIndex()]
            self.exporter.did = self.col.decks.id(name)
        if self.isVerbatim:
            name = time.strftime("-%Y-%m-%d@%H-%M-%S",
                                 time.localtime(time.time()))
            deck_name = _("collection")+name
        else:
            # Get deck name and remove invalid filename characters
            deck_name = self.decks[self.frm.deck.currentIndex()]
            deck_name = re.sub('[\\\\/?<>:*|"^]', '_', deck_name)

        if not self.isVerbatim and self.isApkg and self.exporter.includeSched and self.col.schedVer() == 2:
            showInfo("Please switch to the regular scheduler before exporting a single deck .apkg with scheduling.")
            return

        filename = '{0}{1}'.format(deck_name, self.exporter.ext)
        while 1:
            file = getSaveFile(self, _("Export"), "export",
                               self.exporter.key, self.exporter.ext,
                               fname=filename)
            if not file:
                return
            if checkInvalidFilename(os.path.basename(file), dirsep=False):
                continue
            break
        self.hide()
        if file:
            self.mw.progress.start(immediate=True)
            try:
                f = open(file, "wb")
                f.close()
            except (OSError, IOError) as e:
                showWarning(_("Couldn't save file: %s") % str(e))
            else:
                os.unlink(file)
                exportedMedia = lambda cnt: self.mw.progress.update(
                        label=ngettext("Exported %d media file",
                                       "Exported %d media files", cnt) % cnt
                        )
                addHook("exportedMediaFiles", exportedMedia)
                self.exporter.exportInto(file)
                remHook("exportedMediaFiles", exportedMedia)
                period = 3000
                if self.isVerbatim:
                    msg = _("Collection exported.")
                else:
                    if self.isTextNote:
                        msg = ngettext("%d note exported.", "%d notes exported.",
                                    self.exporter.count) % self.exporter.count
                    else:
                        msg = ngettext("%d card exported.", "%d cards exported.",
                                    self.exporter.count) % self.exporter.count
                tooltip(msg, period=period)
            finally:
                self.mw.progress.finish()
        QDialog.accept(self)
