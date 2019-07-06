from .init import onEmptyCards

from aqt.main import AnkiQt
from aqt import mw
AnkiQt.onEmptyCards = onEmptyCards
mw.form.actionEmptyCards.triggered.disconnect()
mw.form.actionEmptyCards.triggered.connect(mw.onEmptyCards)
