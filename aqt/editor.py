# -*- coding: utf-8 -*-
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
"""
The part of the window used to edit notes. It is used for adding
note, editing existing note, and as the lower part of the browser.

"""

import re
import urllib.request, urllib.parse, urllib.error
import warnings
import html
import mimetypes
import base64
import unicodedata
import json

from anki.lang import _
from aqt.qt import *
from anki.utils import isWin, namedtmp, stripHTMLMedia, \
    checksum
import anki.sound
from anki.hooks import runHook, runFilter, addHook
from aqt.sound import getAudio
from aqt.webview import AnkiWebView
from aqt.utils import shortcut, showInfo, showWarning, getFile, \
    openHelp, tooltip, qtMenuShortcutWorkaround
import aqt
from bs4 import BeautifulSoup
import requests
from anki.sync import AnkiRequestsClient

pics = ("jpg", "jpeg", "png", "tif", "tiff", "gif", "svg", "webp")
audio =  ("wav", "mp3", "ogg", "flac", "mp4", "swf", "mov", "mpeg", "mkv", "m4a", "3gp", "spx", "oga", "webm")

_html = """
<style>
html { background: %s; }
#topbutsOuter { background: %s; }
</style>
<div id="topbutsOuter"><div id="topbuts" class="clearfix">%s</div></div>
<div id="fields"></div>
<div id="dupes" style="display:none;"><a href="#" onclick="pycmd('dupes');return false;">%s</a></div>
"""

# caller is responsible for resetting note on reset
class Editor:
    """
    _links -- associate to each javascript command an action to do. ATTENTION: it is directly a function, and not a method from this class. Thus if you override the method, the function is not automatically modified.
    addMode -- Whether editor is called from addcard.py
    currentField -- The index of the field currently selected. Or None if no fiel is selected.
    card -- the card selected in the browser/in the edit window
    """
    def __init__(self, mw, widget, parentWindow, addMode=False):
        """TODO

        addMode -- Whether editor is called from addcard.py"""
        self.mw = mw
        self.widget = widget
        self.parentWindow = parentWindow
        self.note = None
        self.model= None
        self.addMode = addMode
        self.currentField = None
        # current card, for card layout
        self.card = None
        self.setupOuter()
        self.setupWeb()
        self.setupShortcuts()
        self.setupTagsLine()

    # Initial setup
    ############################################################

    def setupOuter(self):
        l = QVBoxLayout()
        l.setContentsMargins(0,0,0,0)
        l.setSpacing(0)
        self.widget.setLayout(l)
        self.outerLayout = l

    def setupWeb(self):
        self.web = EditorWebView(self.widget, self)
        self.web.title = "editor"
        self.web.allowDrops = True
        self.web.onBridgeCmd = self.onBridgeCmd
        self.outerLayout.addWidget(self.web, 1)

        # List of buttons on top right of editor
        righttopbtns = list()
        righttopbtns.append(self._addButton('text_bold', 'bold', _("Bold text (Ctrl+B)"), id='bold'))
        righttopbtns.append(self._addButton('text_italic', 'italic', _("Italic text (Ctrl+I)"), id='italic'))
        righttopbtns.append(self._addButton('text_under', 'underline', _("Underline text (Ctrl+U)"), id='underline'))
        righttopbtns.append(self._addButton('text_super', 'super', _("Superscript (Ctrl++)"), id='superscript'))
        righttopbtns.append(self._addButton('text_sub', 'sub', _("Subscript (Ctrl+=)"), id='subscript'))
        righttopbtns.append(self._addButton('text_clear', 'clear', _("Remove formatting (Ctrl+R)")))
        # The color selection buttons do not use an icon so the HTML must be specified manually
        tip = _("Set foreground colour (F7)")
        righttopbtns.append('''<button tabindex=-1 class=linkb title="{}"
            type="button" onclick="pycmd('colour');return false;">
            <div id=forecolor style="display:inline-block; background: #000;border-radius: 5px;"
            class=topbut></div></button>'''.format(tip))
        tip = _("Change colour (F8)")
        righttopbtns.append('''<button tabindex=-1 class=linkb title="{}"
            type="button" onclick="pycmd('changeCol');return false;">
            <div style="display:inline-block; border-radius: 5px;"
            class="topbut rainbow"></div></button>'''.format(tip))
        righttopbtns.append(self._addButton('text_cloze', 'cloze', _("Cloze deletion (Ctrl+Shift+C)")))
        righttopbtns.append(self._addButton('paperclip', 'attach', _("Attach pictures/audio/video (F3)")))
        righttopbtns.append(self._addButton('media-record', 'record', _("Record audio (F5)")))
        righttopbtns.append(self._addButton('more', 'more'))
        righttopbtns = runFilter("setupEditorButtons", righttopbtns, self)

        # Fields... and Cards... button on top lefts, and
        lefttopbtns = """
                <button title='%(fldsTitle)s' onclick="pycmd('fields')">%(flds)s...</button>
                <button title='%(cardsTitle)s' onclick="pycmd('cards')">%(cards)s...</button>
        """%dict(flds=_("Fields"), cards=_("Cards"),
                   fldsTitle=_("Customize Fields"),
                   cardsTitle=shortcut(_("Customize Card Templates (Ctrl+L)")))
        topbuts= """
            <div id="topbutsleft" style="float:left;">
                %(lefttopbtns)s
            </div>
            <div id="topbutsright" style="float:right;">
                %(rightbts)s
            </div>
        """ % dict(lefttopbtns = lefttopbtns, rightbts="".join(righttopbtns))
        bgcol = self.mw.app.palette().window().color().name()
        # then load page
        html = _html % (
            bgcol, bgcol,
            topbuts,
            _("Show Duplicates"))
        self.web.stdHtml(html,
                         css=["editor.css"],
                         js=["jquery.js", "editor.js"])

    # Top buttons
    ######################################################################

    def resourceToData(self, path):
        """Convert a file (specified by a path) into a data URI."""
        if not os.path.exists(path):
            raise FileNotFoundError
        mime, _ = mimetypes.guess_type(path)
        with open(path, 'rb') as fp:
            data = fp.read()
            data64 = b''.join(base64.encodebytes(data).splitlines())
            return 'data:%s;base64,%s' % (mime, data64.decode('ascii'))


    def addButton(self, icon, cmd, func, tip="", label="",
                  id=None, toggleable=False, keys=None, disables=True):
        """Assign func to bridge cmd, register shortcut, return button"""
        if cmd not in self._links:
            self._links[cmd] = func
        if keys:
            QShortcut(QKeySequence(keys), self.widget,
                      activated = lambda s=self: func(s))
        btn = self._addButton(icon, cmd, tip=tip, label=label,
                              id=id, toggleable=toggleable, disables=disables)
        return btn

    def _addButton(self, icon, cmd, tip="", label="", id=None, toggleable=False,
                   disables=True):
        """Create a button, with the image icon, or the text of the label, or
        of the cmd. It send the python command cmd.

        icon -- url to the icon. Potentially falsy
        cmd -- python command to call when the button is pressed
        tip -- text to show when the mouse is on the button
        id -- an identifier for the html button
        toggleable -- whether pressing the button should call the js function toggleEditorButton
        disables -- if true, add class "perm" to the btuton

        """
        if icon:
            if icon.startswith("qrc:/"):
                iconstr = icon
            elif os.path.isabs(icon):
                iconstr = self.resourceToData(icon)
            else:
                iconstr = "/_anki/imgs/{}.png".format(icon)
            imgelm = '''<img class=topbut src="{}">'''.format(iconstr)
        else:
            imgelm = ""
        if label or not imgelm:
            labelelm = '''<span class=blabel>{}</span>'''.format(label or cmd)
        else:
            labelelm = ""
        if id:
            idstr = 'id={}'.format(id)
        else:
            idstr = ""
        if toggleable:
            toggleScript = 'toggleEditorButton(this);'
        else:
            toggleScript = ''
        tip = shortcut(tip)
        theclass = "linkb"
        if not disables:
            theclass += " perm"
        return ('''<button tabindex=-1 {id} class="{theclass}" type="button" title="{tip}"'''
                ''' onclick="pycmd('{cmd}');{togglesc}return false;">'''
                '''{imgelm}{labelelm}</button>'''.format(
                        imgelm=imgelm, cmd=cmd, tip=tip, labelelm=labelelm, id=idstr,
                        togglesc=toggleScript, theclass=theclass)
                )

    def setupShortcuts(self):
        # if a third element is provided, enable shortcut even when no field selected
        cuts = [
            ("Ctrl+L", self.onCardLayout, True),
            ("Ctrl+B", self.toggleBold),
            ("Ctrl+I", self.toggleItalic),
            ("Ctrl+U", self.toggleUnderline),
            ("Ctrl++", self.toggleSuper),
            ("Ctrl+=", self.toggleSub),
            ("Ctrl+R", self.removeFormat),
            ("F7", self.onForeground),
            ("F8", self.onChangeCol),
            ("Ctrl+Shift+C", self.onCloze),
            ("Ctrl+Shift+Alt+C", self.onCloze),
            ("F3", self.onAddMedia),
            ("F5", self.onRecSound),
            ("Ctrl+T, T", self.insertLatex),
            ("Ctrl+T, E", self.insertLatexEqn),
            ("Ctrl+T, M", self.insertLatexMathEnv),
            ("Ctrl+M, M", self.insertMathjaxInline),
            ("Ctrl+M, E", self.insertMathjaxBlock),
            ("Ctrl+M, C", self.insertMathjaxChemistry),
            ("Ctrl+Shift+X", self.onHtmlEdit),
            ("Ctrl+Shift+T", self.onFocusTags, True)
        ]
        runHook("setupEditorShortcuts", cuts, self)
        for row in cuts:
            if len(row) == 2:
                keys, fn = row
                fn = self._addFocusCheck(fn)
            else:
                keys, fn, _ = row
            QShortcut(QKeySequence(keys), self.widget, activated=fn)

    def _addFocusCheck(self, fn):
        def checkFocus():
            if self.currentField is None:
                return
            fn()
        return checkFocus

    def onFields(self):
        self.saveNow(self._onFields)

    def _onFields(self):
        from aqt.fields import FieldDialog
        FieldDialog(self.mw, self.note, parent=self.parentWindow)

    def onCardLayout(self):
        self.saveNow(self._onCardLayout)

    def _onCardLayout(self):
        from aqt.clayout import CardLayout
        if self.card:
            ord = self.card.ord
        else:
            ord = 0
        CardLayout(self.mw, self.note, ord=ord, parent=self.parentWindow,
               addMode=self.addMode)
        if isWin:
            self.parentWindow.activateWindow()

    # JS->Python bridge
    ######################################################################

    def onBridgeCmd(self, cmd):
        if not self.note or not runHook:
            # shutdown
            return
        # focus lost or key/button pressed?
        args = cmd.split(":")
        cmd = args.pop(0)
        if cmd in self._links:
            self._links[cmd](self, *args)
        else:
            print("uncaught cmd", cmd)

    def onBlur(self, *args):
        self.onKeyOrBlur(*args)
        self.currentField = None
        # run any filters
        if runFilter(
            "editFocusLost", False, self.note, ord):
            # something updated the note; update it after a subsequent focus
            # event has had time to fire
            self.mw.progress.timer(100, self.loadNoteKeepingFocus, False)
        else:
            self.checkValid()

    def onKey(self, *args):
        self.onKeyOrBlur(*args)
        runHook("editTimer", self.note)
        self.checkValid()

    def onKeyOrBlur(self, ord, nid, *args):
        ord = int(ord)
        txt = ":".join(args)
        try:
            nid = int(nid)
        except ValueError:
            nid = 0
        if nid != self.note.id:
            print("ignored late blur")
            return
        txt = urllib.parse.unquote(txt)
        txt = unicodedata.normalize("NFC", txt)
        txt = self.mungeHTML(txt)
        # misbehaving apps may include a null byte in the text
        txt = txt.replace("\x00", "")
        # reverse the url quoting we added to get images to display
        txt = self.mw.col.media.escapeImages(txt, unescape=True)
        self.note.fields[ord] = txt
        if not self.addMode:
            self.note.flush()
            self.mw.requireReset()

    def onFocus(self):
        # focused into field?
        (type, num) = cmd.split(":", 1)
        self.currentField = int(num)
        runHook("editFocusGained", self.note, self.currentField)

    def mungeHTML(self, txt):
        if txt in ('<br>', '<div><br></div>'):
            return ''
        return txt

    # Setting/unsetting the current note
    ######################################################################

    def setNote(self, note, hide=True, focusTo=None):
        """Make `note` the current note.
        It's used when a new note should be set in place, or when the model change.

        if note is Falsy:
        Remove tags's line.


        keyword arguments:
        note -- the new note in the editor
        hide -- whether to hide the current widget
        focusTo -- in which field should the focus appear
        """
        self.note = note
        if self.note:
            self.model = note.model()
            self.ccSpin.setValue(self.model.get("number of columns", 1))
            self.loadNote(focusTo=focusTo)
        else:
            self.model = None
            self.hideCompleters()
            if hide:
                self.widget.hide()

    def loadNoteKeepingFocus(self):
        self.loadNote(self.currentField)

    def loadNote(self, focusTo=None):
        """Todo

        focusTo -- Whether focus should be set to some field."""
        if not self.note:
            return

        # Triple, for each fields, with (field name, field
        # content modified so that it's image's url can be
        # used locally, and whether it is on its own line)
        data = [(fld,
                 self.mw.col.media.escapeImages(val),
                 self.model["flds"][ord].get("Line alone", False),
                 self.model["flds"][ord].get("sticky", False)
        ) for ord, (fld, val) in enumerate(self.note.items())]
        self.widget.show()
        self.updateTags()

        def oncallback(arg):
            if not self.note:
                return
            self.setupForegroundButton()
            self.checkValid()
            if focusTo is not None:
                self.web.setFocus()
            runHook("loadNote", self)

        self.web.evalWithCallback("setFields(%s,%d); setFonts(%s); focusField(%s); setNoteId(%s)" % (
            json.dumps(data),
            self.model.get("number of columns", 1),
            json.dumps(self.fonts()),
            json.dumps(focusTo),
            json.dumps(self.note.id)),
                                  oncallback)

    def fonts(self):
        return [(runFilter("mungeEditingFontName", f['font']),
                 f['size'], f['rtl'])
                for f in self.model['flds']]

    def saveNow(self, callback, keepFocus=False):
        "Save unsaved edits then call callback()."
        if not self.note:
             # calling code may not expect the callback to fire immediately
            self.mw.progress.timer(10, callback, False)
            return
        self.saveTags()
        self.web.evalWithCallback(f"saveNow({keepFocus})", lambda res: callback())

    def checkValid(self):
        cols = []
        err = None
        for f in self.note.fields:
            cols.append("#fff")
        err = self.note.dupeOrEmpty()
        if err == 2:
            cols[0] = "#fcc"
            self.web.eval("showDupes();")
        else:
            self.web.eval("hideDupes();")
        self.web.eval("setBackgrounds(%s);" % json.dumps(cols))

    def showDupes(self):
        contents = stripHTMLMedia(self.note.fields[0])
        browser = aqt.dialogs.open("Browser", self.mw)
        browser.form.searchEdit.lineEdit().setText(
            '"dupe:%s,%s"' % (self.model['id'],
                              contents))
        browser.onSearchActivated()

    def fieldsAreBlank(self):
        if not self.note:
            return True
        m = self.model
        for c, f in enumerate(self.note.fields):
            if f and not m['flds'][c]['sticky']:
                return False
        return True

    def cleanup(self):
        self.setNote(None)
        # prevent any remaining evalWithCallback() events from firing after C++ object deleted
        self.web = None

    # HTML editing
    ######################################################################

    def onHtmlEdit(self):
        field = self.currentField
        self.saveNow(lambda: self._onHtmlEdit(field))

    def _onHtmlEdit(self, field):
        d = QDialog(self.widget)
        form = aqt.forms.edithtml.Ui_Dialog()
        form.setupUi(d)
        form.buttonBox.helpRequested.connect(lambda: openHelp("editor"))
        form.textEdit.setPlainText(self.note.fields[field])
        form.textEdit.moveCursor(QTextCursor.End)
        d.exec_()
        html = form.textEdit.toPlainText()
        # filter html through beautifulsoup so we can strip out things like a
        # leading </div>
        with warnings.catch_warnings() as w:
            warnings.simplefilter('ignore', UserWarning)
            html = str(BeautifulSoup(html, "html.parser"))
        self.note.fields[field] = html
        self.note.flush()
        self.loadNote(focusTo=field)

    def setupTagsLine(self):
        g = QGroupBox(self.widget)
        g.setFlat(True)
        tabLine = QHBoxLayout()
        tabLine.setSpacing(12)
        tabLine.setContentsMargins(6,6,6,6)

        self.setupTags(tabLine)
        self.setupNumberColum(tabLine)

        self.outerLayout.addWidget(g)
        g.setLayout(tabLine)


    # Column handling
    ######################################################################

    def onColumnCountChanged(self, count):
        "Save column count to settings and re-draw with new count."
        self.model["number of columns"] = count
        self.mw.col.models.save(self.model, recomputeReq=False)
        self.loadNote()

    def setupNumberColum(self, tabLine):
        label = QLabel("Columns:", self.widget)
        tabLine.addWidget(label)
        self.ccSpin = QSpinBox(self.widget)
        tabLine.addWidget(self.ccSpin)
        self.ccSpin.setMinimum(1)
        self.ccSpin.valueChanged.connect(lambda value: self.onColumnCountChanged(value))

    def onToggleLineAlone(self, fieldNumber):
        fieldNumber = int(fieldNumber)
        fieldObject = self.model['flds'][fieldNumber]
        self.mw.col.models.save(self.model, recomputeReq=False)
        fieldObject["Line alone"] = not fieldObject.get("Line alone", False)
        self.loadNote()

    def onFroze(self, fieldNumber):
        fieldNumber = int(fieldNumber)
        fieldObject = self.model['flds'][fieldNumber]
        fieldObject["sticky"] = not fieldObject.get("sticky", False)
        self.mw.col.models.save(self.model)
        self.loadNote()

    # Tag handling
    ######################################################################

    def setupTags(self, tabLine):
        import aqt.tagedit
        # tags
        tagLabel = QLabel(_("Tags"))
        tabLine.addWidget(tagLabel)
        self.tags = aqt.tagedit.TagEdit(self.widget)
        self.tags.lostFocus.connect(self.saveTags)
        self.tags.setToolTip(shortcut(_("Jump to tags with Ctrl+Shift+T")))
        tabLine.addWidget(self.tags)

    def updateTags(self):
        if self.tags.col != self.mw.col:
            self.tags.setCol(self.mw.col)
        if not self.tags.text() or not self.addMode:
            self.tags.setText(self.note.stringTags().strip())

    def saveTags(self):
        if not self.note:
            return
        tagsTxt = unicodedata.normalize("NFC", self.tags.text())
        self.note.tags = self.mw.col.tags.canonify(
            self.mw.col.tags.split(tagsTxt))
        self.tags.setText(self.mw.col.tags.join(self.note.tags).strip())
        if not self.addMode:
            self.note.flush()
        runHook("tagsUpdated", self.note)

    def saveAddModeVars(self):
        """During creation of new notes, save tags to the note's model"""
        if self.addMode:
            # save tags to model
            self.model['tags'] = self.note.tags
            self.mw.col.models.save(self.model, recomputeReq=False)

    def hideCompleters(self):
        "Remove tags's line"
        self.tags.hideCompleter()

    def onFocusTags(self):
        self.tags.setFocus()

    # Format buttons
    ######################################################################

    def toggleBold(self):
        self.web.eval("setFormat('bold');")

    def toggleItalic(self):
        self.web.eval("setFormat('italic');")

    def toggleUnderline(self):
        self.web.eval("setFormat('underline');")

    def toggleSuper(self):
        self.web.eval("setFormat('superscript');")

    def toggleSub(self):
        self.web.eval("setFormat('subscript');")

    def removeFormat(self):
        self.web.eval("setFormat('removeFormat');")

    def onCloze(self):
        self.saveNow(self._onCloze, keepFocus=True)

    def _onCloze(self):
        # check that the model is set up for cloze deletion
        if not re.search('{{(.*:)*cloze:',self.model['tmpls'][0]['qfmt']):
            if self.addMode:
                tooltip(_("Warning, cloze deletions will not work until "
                "you switch the type at the top to Cloze."))
            else:
                showInfo(_("""\
To make a cloze deletion on an existing note, you need to change it \
to a cloze type first, via Edit>Change Note Type."""))
                return
        # find the highest existing cloze
        highest = 0
        for name, val in list(self.note.items()):
            m = re.findall(r"\{\{c(\d+)::", val)
            if m:
                highest = max(highest, sorted([int(x) for x in m])[-1])
        # reuse last?
        if not self.mw.app.keyboardModifiers() & Qt.AltModifier:
            highest += 1
        # must start at 1
        highest = max(1, highest)
        self.web.eval("wrap('{{c%d::', '}}');" % highest)

    # Foreground colour
    ######################################################################

    def setupForegroundButton(self):
        self.fcolour = self.mw.pm.profile.get("lastColour", "#00f")
        self.onColourChanged()

    # use last colour
    def onForeground(self):
        self._wrapWithColour(self.fcolour)

    # choose new colour
    def onChangeCol(self):
        new = QColorDialog.getColor(QColor(self.fcolour), None)
        # native dialog doesn't refocus us for some reason
        self.parentWindow.activateWindow()
        if new.isValid():
            self.fcolour = new.name()
            self.onColourChanged()
            self._wrapWithColour(self.fcolour)

    def _updateForegroundButton(self):
        self.web.eval("setFGButton('%s')" % self.fcolour)

    def onColourChanged(self):
        self._updateForegroundButton()
        self.mw.pm.profile['lastColour'] = self.fcolour

    def _wrapWithColour(self, colour):
        self.web.eval("setFormat('forecolor', '%s')" % colour)

    # Audio/video/images
    ######################################################################

    def onAddMedia(self):
        key = (_("Media") +
               " (*.jpg *.png *.gif *.tiff *.svg *.tif *.jpeg "+
               "*.mp3 *.ogg *.wav *.avi *.ogv *.mpg *.mpeg *.mov *.mp4 " +
               "*.mkv *.ogx *.ogv *.oga *.flv *.swf *.flac *.webp *.m4a)")
        def accept(file):
            self.addMedia(file, canDelete=True)
        file = getFile(self.widget, _("Add Media"), accept, key, key="media")
        self.parentWindow.activateWindow()

    def addMedia(self, path, canDelete=False):
        html = self._addMedia(path, canDelete)
        self.web.eval("setFormat('inserthtml', %s);" % json.dumps(html))

    def _addMedia(self, path, canDelete=False):
        "Add to media folder and return local img or sound tag."
        # copy to media folder
        fname = self.mw.col.media.addFile(path)
        # remove original?
        if canDelete and self.mw.pm.profile['deleteMedia']:
            if os.path.abspath(fname) != os.path.abspath(path):
                try:
                    os.unlink(path)
                except:
                    pass
        # return a local html link
        return self.fnameToLink(fname)

    def _addMediaFromData(self, fname, data):
        return self.mw.col.media.writeData(fname, data)

    def onRecSound(self):
        try:
            file = getAudio(self.widget)
        except Exception as e:
            showWarning(_(
                "Couldn't record audio. Have you installed 'lame'?") +
                        "\n\n" + repr(str(e)))
            return
        if file:
            self.addMedia(file)

    # Media downloads
    ######################################################################

    def urlToLink(self, url):
        fname = self.urlToFile(url)
        if not fname:
            return None
        return self.fnameToLink(fname)

    def fnameToLink(self, fname):
        ext = fname.split(".")[-1].lower()
        if ext in pics:
            name = urllib.parse.quote(fname.encode("utf8"))
            return '<img src="%s">' % name
        else:
            anki.sound.clearAudioQueue()
            anki.sound.play(fname)
            return '[sound:%s]' % fname

    def urlToFile(self, url):
        l = url.lower()
        for suffix in pics+audio:
            if l.endswith("." + suffix):
                return self._retrieveURL(url)
        # not a supported type
        return

    def isURL(self, s):
        s = s.lower()
        return (s.startswith("http://")
            or s.startswith("https://")
            or s.startswith("ftp://")
            or s.startswith("file://"))

    def inlinedImageToFilename(self, txt):
        prefix = "data:image/"
        suffix = ";base64,"
        for ext in ("jpg", "jpeg", "png", "gif"):
            fullPrefix = prefix + ext + suffix
            if txt.startswith(fullPrefix):
                b64data = txt[len(fullPrefix):].strip()
                data = base64.b64decode(b64data, validate=True)
                if ext == "jpeg":
                    ext = "jpg"
                return self._addPastedImage(data, "."+ext)

        return ""

    def inlinedImageToLink(self, src):
        fname = self.inlinedImageToFilename(src)
        if fname:
            return self.fnameToLink(fname)

        return ""

    # ext should include dot
    def _addPastedImage(self, data, ext):
        # hash and write
        csum = checksum(data)
        fname = "{}-{}{}".format("paste", csum, ext)
        return self._addMediaFromData(fname, data)

    def _retrieveURL(self, url):
        "Download file into media folder and return local filename or None."
        # urllib doesn't understand percent-escaped utf8, but requires things like
        # '#' to be escaped.
        url = urllib.parse.unquote(url)
        if url.lower().startswith("file://"):
            url = url.replace("%", "%25")
            url = url.replace("#", "%23")
            local = True
        else:
            local = False
        # fetch it into a temporary folder
        self.mw.progress.start(
            immediate=not local, parent=self.parentWindow)
        ct = None
        try:
            if local:
                req = urllib.request.Request(url, None, {
                    'User-Agent': 'Mozilla/5.0 (compatible; Anki)'})
                filecontents = urllib.request.urlopen(req).read()
            else:
                reqs = AnkiRequestsClient()
                reqs.timeout = 30
                r = reqs.get(url)
                if r.status_code != 200:
                    showWarning(_("Unexpected response code: %s") % r.status_code)
                    return
                filecontents = r.content
                ct = r.headers.get("content-type")
        except urllib.error.URLError as e:
            showWarning(_("An error occurred while opening %s") % e)
            return
        except requests.exceptions.RequestException as e:
            showWarning(_("An error occurred while opening %s") % e)
            return
        finally:
            self.mw.progress.finish()
        # strip off any query string
        url = re.sub(r"\?.*?$", "", url)
        path = urllib.parse.unquote(url)
        return self.mw.col.media.writeData(path, filecontents, typeHint=ct)

    # Paste/drag&drop
    ######################################################################

    removeTags = ["script", "iframe", "object", "style"]

    def _pastePreFilter(self, html, internal):
        with warnings.catch_warnings() as w:
            warnings.simplefilter('ignore', UserWarning)
            doc = BeautifulSoup(html, "html.parser")

        if not internal:
            for tag in self.removeTags:
                for node in doc(tag):
                    node.decompose()

            # convert p tags to divs
            for node in doc("p"):
                node.name = "div"

        for tag in doc("img"):
            try:
                src = tag['src']
            except KeyError:
                # for some bizarre reason, mnemosyne removes src elements
                # from missing media
                continue

            # in internal pastes, rewrite mediasrv references to relative
            if internal:
                m = re.match(r"http://127.0.0.1:\d+/(.*)$", src)
                if m:
                    tag['src'] = m.group(1)
            else:
                # in external pastes, download remote media
                if self.isURL(src):
                    fname = self._retrieveURL(src)
                    if fname:
                        tag['src'] = fname
                elif src.startswith("data:image/"):
                    # and convert inlined data
                    tag['src'] = self.inlinedImageToFilename(src)

        html = str(doc)
        return html

    def doPaste(self, html, internal, extended=False):
        html = self._pastePreFilter(html, internal)
        if extended:
            extended = "true"
        else:
            extended = "false"
        self.web.eval("pasteHTML(%s, %s, %s);" % (
            json.dumps(html), json.dumps(internal), extended))

    def doDrop(self, html, internal):
        self.web.evalWithCallback("makeDropTargetCurrent();",
                                  lambda _: self.doPaste(html, internal))

    def onPaste(self):
        self.web.onPaste()

    def onCutOrCopy(self):
        self.web.flagAnkiText()

    # Advanced menu
    ######################################################################

    def onAdvanced(self):
        m = QMenu(self.mw)
        a = m.addAction(_("MathJax inline"))
        a.triggered.connect(self.insertMathjaxInline)
        a.setShortcut(QKeySequence("Ctrl+M, M"))
        a = m.addAction(_("MathJax block"))
        a.triggered.connect(self.insertMathjaxBlock)
        a.setShortcut(QKeySequence("Ctrl+M, E"))
        a = m.addAction(_("MathJax chemistry"))
        a.triggered.connect(self.insertMathjaxChemistry)
        a.setShortcut(QKeySequence("Ctrl+M, C"))
        a = m.addAction(_("LaTeX"))
        a.triggered.connect(self.insertLatex)
        a.setShortcut(QKeySequence("Ctrl+T, T"))
        a = m.addAction(_("LaTeX equation"))
        a.triggered.connect(self.insertLatexEqn)
        a.setShortcut(QKeySequence("Ctrl+T, E"))
        a = m.addAction(_("LaTeX math env."))
        a.triggered.connect(self.insertLatexMathEnv)
        a.setShortcut(QKeySequence("Ctrl+T, M"))
        a = m.addAction(_("Edit HTML"))
        a.triggered.connect(self.onHtmlEdit)
        a.setShortcut(QKeySequence("Ctrl+Shift+X"))

        qtMenuShortcutWorkaround(m)

        m.exec_(QCursor.pos())

    # LaTeX
    ######################################################################

    def insertLatex(self):
        self.web.eval("wrap('[latex]', '[/latex]');")

    def insertLatexEqn(self):
        self.web.eval("wrap('[$]', '[/$]');")

    def insertLatexMathEnv(self):
        self.web.eval("wrap('[$$]', '[/$$]');")

    def insertMathjaxInline(self):
        self.web.eval("wrap('\\\\(', '\\\\)');")

    def insertMathjaxBlock(self):
        self.web.eval("wrap('\\\\[', '\\\\]');")

    def insertMathjaxChemistry(self):
        self.web.eval("wrap('\\\\(\\\\ce{', '}\\\\)');")

    # Links from HTML
    ######################################################################

    _links = dict(
        fields=onFields,
        cards=onCardLayout,
        bold=toggleBold,
        italic=toggleItalic,
        underline=toggleUnderline,
        super=toggleSuper,
        sub=toggleSub,
        clear=removeFormat,
        colour=onForeground,
        changeCol=onChangeCol,
        cloze=onCloze,
        attach=onAddMedia,
        record=onRecSound,
        more=onAdvanced,
        dupes=showDupes,
        paste=onPaste,
        cutOrCopy=onCutOrCopy,
        key=onKey,
        blur=onBlur,
        toggleLineAlone=onToggleLineAlone,
        toggleFroze=onFroze,
        #mceTrigger=onMceTrigger,
    )

# Pasting, drag & drop, and keyboard layouts
######################################################################

class EditorWebView(AnkiWebView):

    def __init__(self, parent, editor):
        AnkiWebView.__init__(self)
        self.editor = editor
        self.strip = self.editor.mw.pm.profile['stripHTML']
        self.setAcceptDrops(True)
        self._markInternal = False
        clip = self.editor.mw.app.clipboard()
        clip.dataChanged.connect(self._onClipboardChange)

    def _onClipboardChange(self):
        if self._markInternal:
            self._markInternal = False
            self._flagAnkiText()

    def onCut(self):
        self.triggerPageAction(QWebEnginePage.Cut)

    def onCopy(self):
        self.triggerPageAction(QWebEnginePage.Copy)

    def _onPaste(self, mode):
        extended = self.editor.mw.app.queryKeyboardModifiers() & Qt.ShiftModifier
        mime = self.editor.mw.app.clipboard().mimeData(mode=mode)
        html, internal = self._processMime(mime)
        if not html:
            return
        self.editor.doPaste(html, internal, extended)

    def onPaste(self):
        self._onPaste(QClipboard.Clipboard)

    def onMiddleClickPaste(self):
        self._onPaste(QClipboard.Selection)

    def dropEvent(self, evt):
        mime = evt.mimeData()

        if evt.source() and mime.hasHtml():
            # don't filterhtml from other fields
            html, internal = mime.html(), True
        else:
            html, internal = self._processMime(mime)

        if not html:
            return

        self.editor.doDrop(html, internal)

    # returns (html, isInternal)
    def _processMime(self, mime):
        # print("html=%s image=%s urls=%s txt=%s" % (
        #     mime.hasHtml(), mime.hasImage(), mime.hasUrls(), mime.hasText()))
        # print("html", mime.html())
        # print("urls", mime.urls())
        # print("text", mime.text())

        # try various content types in turn
        html, internal = self._processHtml(mime)
        if html:
            return html, internal

        # favour url if it's a local link
        if mime.hasUrls() and mime.urls()[0].toString().startswith("file://"):
            types = (self._processUrls, self._processImage, self._processText)
        else:
            types = (self._processImage, self._processUrls, self._processText)

        for fn in types:
            html = fn(mime)
            if html:
                return html, False
        return "", False

    def _processUrls(self, mime):
        if not mime.hasUrls():
            return

        url = mime.urls()[0].toString()
        # chrome likes to give us the URL twice with a \n
        url = url.splitlines()[0]
        return self.editor.urlToLink(url)

    def _processText(self, mime):
        if not mime.hasText():
            return

        txt = mime.text()

        # inlined data in base64?
        if txt.startswith("data:image/"):
            return self.editor.inlinedImageToLink(txt)

        # if the user is pasting an image or sound link, convert it to local
        if self.editor.isURL(txt):
            url = txt.split("\r\n")[0]
            link = self.editor.urlToLink(url)
            if link:
                return link

            # not media; add it as a normal link if pasting with shift
            link = '<a href="{}">{}</a>'.format(
                url, html.escape(txt)
            )
            return link

        # normal text; convert it to HTML
        txt = html.escape(txt)
        txt = txt.replace("\n", "<br>")\
            .replace("\t", " "*4)

        # if there's more than one consecutive space,
        # use non-breaking spaces for the second one on
        def repl(match):
            return match.group(1).replace(" ", "&nbsp;") + " "
        txt = re.sub(" ( +)", repl, txt)

        return txt

    def _processHtml(self, mime):
        if not mime.hasHtml():
            return None, False
        html = mime.html()

        # no filtering required for internal pastes
        if html.startswith("<!--anki-->"):
            return html[11:], True

        return html, False

    def _processImage(self, mime):
        if not mime.hasImage():
            return
        im = QImage(mime.imageData())
        uname = namedtmp("paste")
        if self.editor.mw.pm.profile.get("pastePNG", False):
            ext = ".png"
            im.save(uname+ext, None, 50)
        else:
            ext = ".jpg"
            im.save(uname+ext, None, 80)

        # invalid image?
        path = uname+ext
        if not os.path.exists(path):
            return

        data = open(path, "rb").read()
        fname = self.editor._addPastedImage(data, ext)
        if fname:
            return self.editor.fnameToLink(fname)

    def flagAnkiText(self):
        # be ready to adjust when clipboard event fires
        self._markInternal = True

    def _flagAnkiText(self):
        # add a comment in the clipboard html so we can tell text is copied
        # from us and doesn't need to be stripped
        clip = self.editor.mw.app.clipboard()
        if not isMac and not clip.ownsClipboard():
            return
        mime = clip.mimeData()
        if not mime.hasHtml():
            return
        html = mime.html()
        mime.setHtml("<!--anki-->" + html)
        clip.setMimeData(mime)

    def contextMenuEvent(self, evt):
        m = QMenu(self)
        a = m.addAction(_("Cut"))
        a.triggered.connect(self.onCut)
        a = m.addAction(_("Copy"))
        a.triggered.connect(self.onCopy)
        a = m.addAction(_("Paste"))
        a.triggered.connect(self.onPaste)
        runHook("EditorWebView.contextMenuEvent", self, m)
        m.popup(QCursor.pos())

# QFont returns "Kozuka Gothic Pro L" but WebEngine expects "Kozuka Gothic Pro Light"
# - there may be other cases like a trailing 'Bold' that need fixing, but will
# wait for further reports first.
def fontMungeHack(font):
    return re.sub(" L$", " Light", font)
addHook("mungeEditingFontName", fontMungeHack)
