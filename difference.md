# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## Export notes selected in the Browser (1983204951)
Selects some cards in the browser. Then `Cards>Export cards` allow you
to export the cards. This is similar to exporting a deck, except that
you have more fine control. You can essentially export anything that
you can query in the browser or that you can select.

Note that, if you export a deck, or a selection of cards, and that you
export cards, you are also exporting the notes of those
cards. However, some cards may be missing. When importing those cards,
the missing cards will be generated, and will be totally new. You may
lose data this way.  In the preference "Export siblings of exported
cards" allow you to avoid losing data, by exporting the siblings of
exported cards. The problem being, of course, that you may export
cards in decks you did not select. Thus, importing those cards may
potentially create more decks than expected.
