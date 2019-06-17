# Differences with anki.
This files list the difference between regular anki and this forked
version. It also lists the different options in the Preferences's extra page.

## When changing note type, preserve names (513858554)
If you change a note's type, and the old and the new note have
fields/cards with the same name, then those fields/cards are mapped by
default such that they keep the same name.

In preferences, you can unbox "When changing note type, preserve names
if possible." to recover anki's default behavior, i.e. sending first
element to first one, second to second, etc..
