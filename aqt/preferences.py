# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import datetime, time
from aqt.qt import *
import anki.lang
from aqt.utils import openFolder, openHelp, showInfo, askUser
import aqt
from anki.lang import _

class Preferences(QDialog):

    """
    startdate -- datetime where collection was created. Only in schedV1
    """

    def __init__(self, mw):
        QDialog.__init__(self, mw, Qt.Window)
        self.mw = mw
        self.prof = self.mw.pm.profile
        self.form = aqt.forms.preferences.Ui_Preferences()
        self.form.setupUi(self)
        self.form.buttonBox.button(QDialogButtonBox.Help).setAutoDefault(False)
        self.form.buttonBox.button(QDialogButtonBox.Close).setAutoDefault(False)
        self.form.buttonBox.helpRequested.connect(lambda: openHelp("profileprefs"))
        self.silentlyClose = True
        self.setupLang()
        self.setupCollection()
        self.setupNetwork()
        self.setupBackup()
        self.setupOptions()
        self.setupExtra()
        self.show()

    def accept(self):
        # avoid exception if main window is already closed
        if not self.mw.col:
            return
        self.updateCollection()
        self.updateNetwork()
        self.updateBackup()
        self.updateOptions()
        self.updateExtra()
        self.mw.pm.save()
        self.mw.reset()
        self.done(0)
        aqt.dialogs.markClosed("Preferences")

    def reject(self):
        self.accept()

    # Language
    ######################################################################

    def setupLang(self):
        f = self.form
        f.lang.addItems([x[0] for x in anki.lang.langs])
        f.lang.setCurrentIndex(self.langIdx())
        f.lang.currentIndexChanged.connect(self.onLangIdxChanged)

    def langIdx(self):
        codes = [x[1] for x in anki.lang.langs]
        try:
            return codes.index(anki.lang.getLang())
        except:
            return codes.index("en")

    def onLangIdxChanged(self, idx):
        code = anki.lang.langs[idx][1]
        self.mw.pm.setLang(code)
        showInfo(_("Please restart Anki to complete language change."), parent=self)

    # Collection options
    ######################################################################

    def setupCollection(self):
        import anki.consts as c
        f = self.form
        qc = self.mw.col.conf
        self._setupDayCutoff()
        if isMac:
            f.hwAccel.setVisible(False)
        else:
            f.hwAccel.setChecked(self.mw.pm.glMode() != "software")
        f.lrnCutoff.setValue(qc['collapseTime']/60.0)
        f.timeLimit.setValue(qc['timeLim']/60.0)
        f.showEstimates.setChecked(qc['estTimes'])
        f.showProgress.setChecked(qc['dueCounts'])
        f.nightMode.setChecked(qc.get("nightMode", False))
        f.newSpread.addItems(list(c.newCardSchedulingLabels().values()))
        f.newSpread.setCurrentIndex(qc['newSpread'])
        f.useCurrent.setCurrentIndex(int(not qc.get("addToCur", True)))
        f.dayLearnFirst.setChecked(qc.get("dayLearnFirst", False))
        if self.mw.col.schedVer() != 2:
            f.dayLearnFirst.setVisible(False)
        else:
            f.newSched.setChecked(True)

    def updateCollection(self):
        f = self.form
        d = self.mw.col

        if not isMac:
            wasAccel = self.mw.pm.glMode() != "software"
            wantAccel = f.hwAccel.isChecked()
            if wasAccel != wantAccel:
                if wantAccel:
                    self.mw.pm.setGlMode("auto")
                else:
                    self.mw.pm.setGlMode("software")
                showInfo(_("Changes will take effect when you restart Anki."))

        qc = d.conf
        qc['dueCounts'] = f.showProgress.isChecked()
        qc['estTimes'] = f.showEstimates.isChecked()
        qc['newSpread'] = f.newSpread.currentIndex()
        qc['nightMode'] = f.nightMode.isChecked()
        qc['timeLim'] = f.timeLimit.value()*60
        qc['collapseTime'] = f.lrnCutoff.value()*60
        qc['addToCur'] = not f.useCurrent.currentIndex()
        qc['dayLearnFirst'] = f.dayLearnFirst.isChecked()
        self._updateDayCutoff()
        self._updateSchedVer(f.newSched.isChecked())
        d.setMod()

    # Scheduler version
    ######################################################################

    def _updateSchedVer(self, wantNew):
        haveNew = self.mw.col.schedVer() == 2

        # nothing to do?
        if haveNew == wantNew:
            return

        if haveNew and not wantNew:
            if not askUser(_("This will reset any cards in learning, clear filtered decks, and change the scheduler version. Proceed?")):
                return
            self.mw.col.changeSchedulerVer(1)
            return

        if not askUser(_("The experimental scheduler could cause incorrect scheduling. Please ensure you have read the documentation first. Proceed?")):
            return

        self.mw.col.changeSchedulerVer(2)

    # Day cutoff
    ######################################################################

    def _setupDayCutoff(self):
        if self.mw.col.schedVer() == 2:
            self._setupDayCutoffV2()
        else:
            self._setupDayCutoffV1()

    def _setupDayCutoffV1(self):
        self.startDate = datetime.datetime.fromtimestamp(self.mw.col.crt)
        self.form.dayOffset.setValue(self.startDate.hour)

    def _setupDayCutoffV2(self):
        self.form.dayOffset.setValue(self.mw.col.conf.get("rollover", 4))

    def _updateDayCutoff(self):
        if self.mw.col.schedVer() == 2:
            self._updateDayCutoffV2()
        else:
            self._updateDayCutoffV1()

    def _updateDayCutoffV1(self):
        hrs = self.form.dayOffset.value()
        old = self.startDate
        date = datetime.datetime(
            old.year, old.month, old.day, hrs)
        self.mw.col.crt = int(time.mktime(date.timetuple()))

    def _updateDayCutoffV2(self):
        self.mw.col.conf['rollover'] = self.form.dayOffset.value()

    # Network
    ######################################################################

    def setupNetwork(self):
        self.form.syncOnProgramOpen.setChecked(
            self.prof['autoSync'])
        self.form.syncMedia.setChecked(
            self.prof['syncMedia'])
        if not self.prof['syncKey']:
            self._hideAuth()
        else:
            self.form.syncUser.setText(self.prof.get('syncUser', ""))
            self.form.syncDeauth.clicked.connect(self.onSyncDeauth)

    def _hideAuth(self):
        self.form.syncDeauth.setVisible(False)
        self.form.syncUser.setText("")
        self.form.syncLabel.setText(_("""\
<b>Synchronization</b><br>
Not currently enabled; click the sync button in the main window to enable."""))

    def onSyncDeauth(self):
        self.prof['syncKey'] = None
        self.mw.col.media.forceResync()
        self._hideAuth()

    def updateNetwork(self):
        self.prof['autoSync'] = self.form.syncOnProgramOpen.isChecked()
        self.prof['syncMedia'] = self.form.syncMedia.isChecked()
        if self.form.fullSync.isChecked():
            self.mw.col.modSchema(check=False)
            self.mw.col.setMod()

    # Backup
    ######################################################################

    def setupBackup(self):
        self.form.numBackups.setValue(self.prof['numBackups'])
        self.form.openBackupFolder.linkActivated.connect(self.onOpenBackup)

    def onOpenBackup(self):
        openFolder(self.mw.pm.backupFolder())

    def updateBackup(self):
        self.prof['numBackups'] = self.form.numBackups.value()

    # Basic & Advanced Options
    ######################################################################

    def setupOptions(self):
        self.form.pastePNG.setChecked(self.prof.get("pastePNG", False))

    def updateOptions(self):
        self.prof['pastePNG'] = self.form.pastePNG.isChecked()

    def setupExtra(self):
        """Set in the GUI the preferences related to add-ons forked."""
        self.form.AddMultipleTime.setChecked(
            self.prof.get("AddCardsMultipleTime", True))
        self.form.allowEmptyFirstField.setChecked(
            self.prof.get("allowEmptyFirstField", True))
        self.form.browserOnMissingMedia.setChecked(
            self.prof.get("browserOnMissingMedia", True))
        self.form.EditMultipleTime.setChecked(
            self.prof.get("EditCurrentMultipleTime", True))
        self.form.BrowserMultipleTime.setChecked(
            self.prof.get("BrowserMultipleTime", True))
        self.form.OtherMultipleTime.setChecked(
            self.prof.get("OtherMultipleTime", True))
        self.form.changeModelWithoutFullSync.setChecked(
            self.prof.get("changeModelWithoutFullSync", False))
        self.form.compileLaTeX.setChecked(
            self.prof.get("compileLaTeX", False))
        self.form.complexTemplates.setChecked(
            self.prof.get("complexTemplates", False))
        self.form.exportSiblings.setChecked(
            self.prof.get("exportSiblings", False))
        self.form.EmptyNote.setChecked(
            self.prof.get("keepEmptyNote", True))
        self.form.keepSeenCard.setChecked(
            self.prof.get("keepSeenCard", False))
        self.form.factorAddDay.setValue(
            self.prof.get("factorAddDay", 0.33))
        self.form.factorRemoveDay.setValue(
            self.prof.get("factorRemoveDay", 0.33))
        self.form.noteWithoutCard.setChecked(
            self.prof.get("noteWithoutCard", True))
        self.form.multipleNoteWithSameFirstFieldInImport.setChecked(
            self.prof.get("multipleNoteWithSameFirstFieldInImport", False))
        self.form.newLineInBatchEdit.setChecked(
            self.prof.get("newLineInBatchEdit", False))
        self.form.preserveCreation.setChecked(
            self.prof.get("preserveCreation", True))
        self.form.preserveName.setChecked(
            self.prof.get("preserveName", True))
        self.form.preserveReviewInfo.setChecked(
            self.prof.get("preserveReviewInfo", True))

    def updateExtra(self):
        """Check the preferences related to add-ons forked."""
        self.prof["AddCardsMultipleTime"] = self.form.AddMultipleTime.isChecked()
        self.prof["allowEmptyFirstField"] = self.form.allowEmptyFirstField.isChecked()
        self.prof["browserOnMissingMedia"] = self.form.browserOnMissingMedia.isChecked()
        self.prof["EditCurrentMultipleTime"] = self.form.EditMultipleTime.isChecked()
        self.prof["BrowserMultipleTime"] = self.form.BrowserMultipleTime.isChecked()
        self.prof["OtherMultipleTime"] = self.form.OtherMultipleTime.isChecked()
        self.prof["changeModelWithoutFullSync"] = self.form.changeModelWithoutFullSync.isChecked()
        self.prof["compileLaTeX"] = self.form.xMLName.isChecked()
        self.prof["factorAddDay"] = self.form.factorAddDay.value()
        self.prof["factorRemoveDay"] = self.form.factorRemoveDay.value()
        self.prof["keepSeenCard"] = self.form.keepSeenCard.isChecked()
        self.prof["keepEmptyNote"] = self.form.keepEmptyNote.isChecked()
        self.prof["newLineInBatchEdit"] = self.form.newLineInBatchEdit.isChecked()
        self.prof["noteWithoutCard"] = self.form.noteWithoutCard.isChecked()
        self.prof["multipleNoteWithSameFirstFieldInImport"] = self.form.multipleNoteWithSameFirstFieldInImport.isChecked()
        self.prof["preserveName"] = self.form.preserveName.isChecked()
        self.prof["preserveCreation"] = self.form.preserveCreation.isChecked()
        self.prof["preserveReviewInfo"] = self.form.preserveReviewInfo.isChecked()
        self.prof["exportSiblings"] = self.form.exportSiblings.isChecked()
        self.prof["complexTemplates"] = self.form.complexTemplates.isChecked()
